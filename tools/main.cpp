// pka2xml — decrypt / encrypt Cisco Packet Tracer .pka/.pkt files.
// Derived from https://github.com/mircodz/pka2xml (BSD-2-Clause, see LICENSE.pka2xml).
// Trimmed to file conversion only.

#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iterator>
#include <string>

#include "pka2xml.hpp"

[[noreturn]] static void die(const char *message) {
  std::fprintf(stderr, "%s\n", message);
  std::exit(1);
}

[[noreturn]] static void help() {
  std::printf(R"(usage: pka2xml [ options ]

  -d <in> <out>   decrypt pka/pkt to xml
  -e <in> <out>   encrypt xml to pka/pkt
  --forge <out>   forge authentication file to bypass login

examples:
  pka2xml -d foobar.pka foobar.xml
  pka2xml -e foobar.xml foobar.pka
  pka2xml --forge nets
)");
  std::exit(1);
}

static std::string read_file(const char *path) {
  std::ifstream f{path, std::ios::binary};
  if (!f.is_open()) die("error opening input file");
  return {std::istreambuf_iterator<char>(f), std::istreambuf_iterator<char>()};
}

static void write_file(const char *path, const std::string &data) {
  std::ofstream f{path, std::ios::binary};
  if (!f.is_open()) die("error opening output file");
  f << data;
}

int main(int argc, char *argv[]) {
  if (argc != 4) help();
  const std::string mode = argv[1];
  try {
    if (mode == "-d") {
      write_file(argv[3], pka2xml::decrypt_pka(read_file(argv[2])));
    } else if (mode == "-e") {
      write_file(argv[3], pka2xml::encrypt_pka(read_file(argv[2])));
    } else if (mode == "--forge" && argc == 3) {
      write_file(argv[2], pka2xml::encrypt_nets("foobar~foobar~foobar~foobar~1700000000"));
    }
    else {
      help();
    }
  } catch (...) {
    die("error during the processing of the files, make sure the input files are valid");
  }
}
