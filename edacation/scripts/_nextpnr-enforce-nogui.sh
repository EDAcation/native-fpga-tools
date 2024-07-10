temp_script="$(mktemp)"

cp "$1" "$temp_script"
sed -i 's/build_gui=.*$/build_gui="OFF"/' "$temp_script"

build_gui="OFF"

source "$temp_script"
