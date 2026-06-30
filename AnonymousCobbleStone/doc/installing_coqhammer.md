# installing coqhammer

opam repo add coq-released https://coq.inria.fr/opam/released   && opam install -y coq-hammer

## installing E prover v 2.6

curl https://github.com/eprover/eprover/archive/refs/tags/E-2.6.tar.gz -L -s -o eprover.tar.gz
tar -xvf eprover.tar.gz
cd eprover-E-2.6
./configure --bindir=~/.local/bin
make
make install
eprover --version

## installing vampire

curl https://github.com/vprover/vampire/releases/download/v4.8casc2023/vampire_z3_rel_static_casc2023_6749.zip -L -s -o vampire.zip
unzip vampire.zip
mv bin/vampire_z3_rel_static_casc2023_6749 ~/.local/bin/vampire
vampire --version

## installing cvc4

curl https://github.com/CVC4/CVC4-archived/releases/download/1.8/cvc4-1.8-x86_64-linux-opt -L -s -o cvc4-1.8-x86_64-linux-opt
mv cvc4-1.8-x86_64-linux-opt cvc4
chmod +x cvc4
mv cvc4 ~/.local/bin/cvc4
cvc4 --version

## installing z3 with tptp

wget https://github.com/Z3Prover/z3/releases/download/z3-4.12.5/z3-4.12.5-arm64-glibc-2.35.zip
unzip z3-4.12.5-arm64-glibc-2.35.zip
cd z3-4.12.5-arm64-glibc-2.35
mv bin/* ~/.local/bin/
sudo cp include/* /usr/local/include
z3 --version

wget https://github.com/Z3Prover/z3/archive/refs/tags/z3-4.12.5.zip
unzip z3-4.12.5.zip 
cd z3-z3-4.12.5/
./configure -p ~/.local
cd build
sudo make
sudo make install
sudo make examples
cp libz3.so ~/.local/lib
set LD_LIBRARY_PATH to include ~/.local/lib
cp z3_tptp ~/.local/bin
z3 --version
z3_tptp --version