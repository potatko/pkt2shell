# Builds tools/pka2xml. Needs Crypto++ and zlib
#   macOS:  brew install cryptopp
#   Debian/Ubuntu: sudo apt install libcrypto++-dev zlib1g-dev
PREFIX ?= $(shell brew --prefix 2>/dev/null || echo /usr)
CXX    ?= c++

tools/pka2xml: tools/main.cpp tools/pka2xml.hpp
	$(CXX) -std=c++17 -O2 -o $@ tools/main.cpp -I$(PREFIX)/include -L$(PREFIX)/lib -lcryptopp -lz

.PHONY: clean
clean:
	rm -f tools/pka2xml
