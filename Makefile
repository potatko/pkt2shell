# Optional: builds the C++ converter cpp/pka2xml (not needed — tools/pkt.py is pure Python).
# Needs Crypto++ and zlib:  macOS: brew install cryptopp   Debian/Ubuntu: sudo apt install libcrypto++-dev zlib1g-dev
PREFIX ?= $(shell brew --prefix 2>/dev/null || echo /usr)
CXX    ?= c++

cpp/pka2xml: cpp/main.cpp cpp/pka2xml.hpp
	$(CXX) -std=c++17 -O2 -o $@ cpp/main.cpp -I$(PREFIX)/include -L$(PREFIX)/lib -lcryptopp -lz

.PHONY: clean
clean:
	rm -f cpp/pka2xml
