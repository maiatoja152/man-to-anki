import subprocess
import json
import re
import gzip
import argparse
import typing
from ankiconnect import invoke_anki_connect
from pathlib import Path

import bs4


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Automatically create Anki flashcards for a given man page",
            )
    parser.add_argument(
        "page",
        type=str,
        help="The name of the man page",
    )
    parser.add_argument(
        "section",
        choices=range(1, 9),
        type=int,
        help="The section number for the man page.",
    )
    parser.add_argument(
        "-d",
        "--description",
        action="store_true",
        help="Create a flashcard for a short description of the man page",
    )
    parser.add_argument(
        "-o",
        "--option",
        type=str,
        nargs=argparse.ONE_OR_MORE,
        help="Create flashcards for command options",
    )
    parser.add_argument(
        "--subcommand",
        action="store_true",
        help="Indicate that this is a man page for a subcommand such as git-commit"
    )
    return parser.parse_args()


def get_config() -> dict[str, typing.Any]:
    with open("config.json") as config_file:
        return json.load(config_file)


def first_letter_capitalize(string: str) -> str:
    return string[0].upper() + string[1:]


def input_one_liner() -> str:
    return input("Manually input one-line description for the page: ")


def get_one_liner(parsed_html: bs4.BeautifulSoup) -> str:
    line: bs4.Tag | bs4.NavigableString | None = parsed_html.find("p")
    if not isinstance(line, bs4.Tag):
        return input_one_liner()

    regex = re.compile(r"\s[-—]\s(.*)")
    match: re.Match | None = regex.search(str(line.string))
    if match is not None:
        return match.group(1)
    else:
        return input_one_liner()


def get_option_dt(
    parsed_html: bs4.BeautifulSoup,
    option: str
) -> bs4.Tag | None:
    for dt in parsed_html.find_all("dt"):
        for strong in dt.find_all("strong"):
            if strong.string == option:
                return dt
    return None


def get_option_title(dt: bs4.Tag, option: str) -> str:
    title: str = "".join(map(str, dt.contents))
    if title == "":
        return input_option_title(option)
    else:
        return title


def get_option_description(dt: bs4.Tag, option: str) -> str:
    dd: bs4.Tag | bs4.NavigableString | None = dt.find_next_sibling("dd")
    if not isinstance(dd, bs4.Tag):
        return input_option_description(option)
    p: bs4.Tag | bs4.NavigableString | None = dd.find("p")
    if not isinstance(p, bs4.Tag):
        return input_option_description(option)
    description: str = "".join(map(str, p.contents))

    if description == "":
        return input_option_description(option)
    else:
        return first_letter_capitalize(description)


def input_option_title(option: str) -> str:
    return input(f"Manually enter an option title for {option}: ")


def input_option_description(option: str) -> str:
    return input(f"Manually enter an option description for {option}: ")


def get_option_info(
    parsed_html: bs4.BeautifulSoup,
    option: str
) -> tuple[str, str]:
    dt: bs4.Tag | None = get_option_dt(parsed_html, option)
    if dt is None:
        return (
            input_option_title(option),
            input_option_description(option),
        )
    return (get_option_title(dt, option), get_option_description(dt, option))


def create_man_html_file(section: int, page: str) -> str:
    """
    Create a file in the Anki collection containing an html conversion of a man
    page. If a file already exists for this page, it will be overwritten.

    Args:
        section (int): man page section
        page (int): man page name

    Returns:
        str: The absolute path to the generated html file
        OR None if the man page could not be found.
    """
    man_file_path: bytes = subprocess.check_output(
        ("man", "--path", str(section), page),
    ).strip()
    man_unzipped_file: bytes = gzip.open(man_file_path).read()

    config = get_config()
    html_file_name: str = f"_man-{section}-{page}.html"
    html_file_path: Path = Path(config["anki-collection"]) / html_file_name
    with open(html_file_path, "w+b") as html_file:
        subprocess.run(
            ("pandoc", "--from", "man", "--to", "html"),
            input=man_unzipped_file,
            stdout=html_file,
            check=True,
        )

    return html_file_path


def add_note(
    deck: str,
    front: str,
    back: str,
    hint: str,
    source: str,
    tags: list
) -> int:
    note = {
        "deckName": deck,
        "modelName": "Basic",
        "fields": {
            "Front": front,
            "Back": back,
            "Hint": hint,
            "Source": source,
        },
        "tags": tags,
    }
    config = get_config()
    return invoke_anki_connect(config["anki-connect-url"], "addNote", note=note)


def add_description_note(description: str, page: str, source: str) -> int:
    config = get_config()
    return add_note(
        deck=config["deck"],
        front=description,
        back=page,
        hint=config["hint-one-liner"],
        source=source,
        tags=config["tags-one-liner"],
    )


def add_option_note(
        option_description: str,
        option_title: str,
        page: str,
        source: str
) -> int:
    config = get_config()
    return add_note(
        deck=config["deck"],
        front=option_description,
        back=option_title,
        hint=config["hint-option-description"].format(page=page),
        source=source,
        tags=config["tags-option-description"],
    )


def gui_browse_notes(note_ids: list[int]) -> list[int]:
    return invoke_anki_connect(
        get_config()["anki-connect-url"],
        "guiBrowse",
        query="nid:" + ",".join(map(str, note_ids))
    )


def main() -> None:
    args: argparse.Namespace = get_args()
    page: str = args.page
    section: int = args.section

    man_html_file_path: str = create_man_html_file(section, page)
    print(f"Created (or updated) an html file for \
    {page}({section}) at: {man_html_file_path}")

    if args.subcommand:
        # For example, turn "git-commit" into "git commit"
        command: str = page.replace("-", " ")
    else:
        command: str = page

    with open(man_html_file_path) as man_html_file:
        soup = bs4.BeautifulSoup(man_html_file, "html.parser")

    source = Path(man_html_file_path).name
    note_ids: list[int] = []
    if args.description:
        note_id: int = add_description_note(
            get_one_liner(soup),
            command,
            source
        )
        print(f"Added one liner note ({note_id})"
            f"for the man page: {command}({section})")
        note_ids.append(note_id)

    if args.option is not None:
        for option in args.option:
            if len(option) == 1:
                option = "-" + option
            else:
                option = "--" + option
            title, description = get_option_info(soup, option)
            note_id = add_option_note(description, title, command, source)
            print(f"Added option description note ({note_id})"
                f"for the man page: {command}({section})")
            note_ids.append(note_id)

    if len(note_ids) > 0:
        gui_browse_notes(note_ids)


if __name__ == "__main__":
    main()