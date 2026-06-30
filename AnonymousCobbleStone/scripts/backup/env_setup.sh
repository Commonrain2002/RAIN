#!/bin/bash

# Update and install dependencies
apt-get update
apt-get -y install --no-install-recommends fish git python3 python3-distutils curl gpg sqlite3 nano

# Clean up
apt-get autoremove -y
apt-get clean -y
rm -rf /var/lib/apt/lists/*

# Install opam
sh <(curl -sL https://raw.githubusercontent.com/ocaml/opam/master/shell/install.sh)

# Disable sandboxing and initialize opam
opam init --disable-sandboxing --auto-setup

# Install coq switches
opam switch create coq-8.12 4.07.1
eval $(opam env --switch=coq-8.12 --set-switch)
opam pin add -y coq 8.12.2
opam install coq-serapi

# Link python3 to /usr/local/bin/python
ln -s /usr/bin/python3 /usr/local/bin/python

# Install gum cli tool
mkdir -p /etc/apt/keyrings
curl -fsSL https://repo.charm.sh/apt/gpg.key | gpg --dearmor -o /etc/apt/keyrings/charm.gpg
echo "deb [signed-by=/etc/apt/keyrings/charm.gpg] https://repo.charm.sh/apt/ * *" | tee /etc/apt/sources.list.d/charm.list
apt-get update
apt-get install -y gum

# Install poetry for python
curl -sSL https://install.python-poetry.org | python3 -

# Print versions and help as in Dockerfile
echo $(opam --version)
echo $(ocaml --version)
echo $(coqc -v)
sertop --help

# If you want to switch to fish shell uncomment the line below
# fish
