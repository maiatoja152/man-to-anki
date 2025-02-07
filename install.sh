quit_on_file_not_found () {
    if [[ ! -f $1 ]] ; then
    echo "$1 not found. Make sure it is in your current working directory."
    exit 1
    fi
}

files="man-to-anki.py ankiconnect.py config.json" 

for file in $files; do
    quit_on_file_not_found $file
done

install_dir="/opt/man-to-anki/"
if [[ ! -d $install_dir ]] ; then
    mkdir -p $install_dir
fi

cp $files $install_dir

echo "Add the following to ~/.bashrc:"
echo "export PATH=\"\$PATH:$install_dir\""