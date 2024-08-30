import sys
import subprocess
import json
import urllib.request
import os.path
import gzip
import argparse
import re

import bs4


def help():
    print("Usage: python cli-to-anki.py command...")
    exit()


def request(action, **params):
    return {"action": action, "params": params, "version": 6}


def invoke(action, **params):
    requestJson = json.dumps(request(action, **params)).encode("utf-8")
    response = json.load(urllib.request.urlopen(
        urllib.request.Request("http://127.0.0.1:8765", requestJson)
    ))
    if len(response) != 2:
        raise Exception("response has an unexpected number of fields")
    if "error" not in response:
        raise Exception("response is missing required error field")
    if "result" not in response:
        raise Exception("response is missing required result field")
    if response["error"] is not None:
        raise Exception(response["error"])
    return response["result"]


def first_letter_capitalize(string: str) -> str:
    return string[0].upper() + string[1:]


def get_user_one_liner() -> str:
    return input("Manually input one-line description for the page: ")


def get_one_liner(parsed_html: bs4.BeautifulSoup) -> str:
    line: bs4.Tag | bs4.NavigableString | None = parsed_html.find("p")
    assert line is not bs4.NavigableString
    if line is None:
        return get_user_one_liner()

    result: str = str(line.string)
    substring: str = " - "
    substring_index: int = result.find(substring)
    if substring_index != -1:
        result = result[substring_index + len(substring):]
        return first_letter_capitalize(result)
    else:
        return get_user_one_liner()


def get_option_dt(
    parsed_html: bs4.BeautifulSoup,
    option: str
) -> bs4.Tag | None:
    dt_list: bs4.ResultSet = parsed_html.find_all("dt")
    for dt in dt_list:
        strongs: bs4.ResultSet = dt.find_all("strong")
        for strong in strongs:
            string: str = str(strong.string)
            if string == option:
                return dt
    return None


def get_option_title(dt: bs4.Tag) -> str | None:
    title: str = ""
    contents = dt.contents
    for content in contents:
        title += str(content)

    if title == "":
        return None
    else:
        return title


def get_option_description(dt: bs4.Tag) -> str | None:
    dd: bs4.Tag | bs4.NavigableString | None = dt.find_next_sibling("dd")
    if dd is None:
        return None
    p: bs4.Tag | None = dd.find("p")
    if p is None:
        return None
    contents = p.contents
    description: str = ""
    for content in contents:
        description += str(content)

    if description == "":
        return None
    else:
        return first_letter_capitalize(description)


def get_user_option_title(option: str) -> str:
    return input(f"Manually enter an option title for {option}: ")


def get_user_option_description(option: str) -> str:
    return input(f"Manually enter an option description for {option}: ")


def get_option_info(
    parsed_html: bs4.BeautifulSoup,
    option: str
) -> tuple[str, str]:
    dt: bs4.Tag | None = get_option_dt(parsed_html, option)
    if dt is None:
        return (
            get_user_option_title(option),
            get_user_option_description(option),
        )

    title: str | None = get_option_title(dt)
    if title is None:
        title = get_user_option_title(option)
    description: str | None = get_option_description(dt)
    if description is None:
        description = get_user_option_description(option)

    return (title, description)


def create_man_html_file(section: int, page: str) -> str | None:
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
    try:
        man_file_path: bytes = subprocess.check_output(
            ("man", "--path", str(section), page),
        ).strip()
    except subprocess.CalledProcessError:
        return None
    man_unzipped_file: bytes = gzip.open(man_file_path).read()

    anki_collection_dir = config["anki-collection"]
    html_file_name: str = f"_man-{section}-{page}.html"
    html_file_path: str = os.path.join(anki_collection_dir, html_file_name)
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
    return invoke("addNote", note=note)


parser: argparse.ArgumentParser = argparse.ArgumentParser(
    description="Automatically create Anki flashcards for a given man page",
        )
parser.add_argument(
    "page",
    help="The name of the man page",
)
parser.add_argument(
    "section",
    choices=range(1, 10),
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
    nargs=argparse.ONE_OR_MORE,
    help="Create flashcards for command options",
)

with open(os.path.join(os.path.dirname(__file__), "config.json"))\
        as config_file:
    config: dict = json.load(config_file)

namespace: argparse.Namespace = parser.parse_args(sys.argv[1:])
page: str = namespace.page
section: int = namespace.section

man_html_file_path: str | None = create_man_html_file(section, page)
if man_html_file_path is None:
    print(f"Could not find a man page for {page}({section})")
    exit(1)
print(f"Created (or updated) an html file for \
{page}({section}) at: {man_html_file_path}")

with open(man_html_file_path) as man_html_file:
    parsed_html = bs4.BeautifulSoup(man_html_file, "html.parser")

source = os.path.basename(man_html_file_path)
noteIDs: list[str] = []
result: int = 0
if namespace.description:
    result = add_note(
        deck=config["deck"],
        front=get_one_liner(parsed_html),
        back=page,
        hint=config["hint-one-liner"],
        source=source,
        tags=config["tags-one-liner"],
    )
    print(f"Added one liner note ({result}) \
for the man page: {page}({section})")
    noteIDs.append(str(result))

if namespace.option is not None:
    for option in namespace.option:
        if len(option) == 1:
            option = "-" + option
        else:
            option = "--" + option
        option_info: tuple[str, str] = get_option_info(parsed_html, option)
        result = add_note(
            deck=config["deck"],
            front=option_info[1],
            back=option_info[0],
            hint=config["hint-option-description"].format(page=page),
            source=source,
            tags=config["tags-option-description"],
        )
        print(f"Added option description note ({result}) \
for the man page: {page}({section})")
        noteIDs.append(str(result))

if len(noteIDs) > 0:
    query: str = "nid:" + ",".join(noteIDs)
    invoke("guiBrowse", query=query)
