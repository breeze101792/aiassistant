# NixOS development shell.
#
# NixOS has no /usr/lib, so a wheel with compiled extensions (numpy, sounddevice,
# tiktoken) cannot find libstdc++ or libz at load time and fails with
# "cannot open shared object file". This puts the libraries on the loader path
# and keeps them in this shell's closure, so `nix-collect-garbage` cannot remove
# them from under a working venv -- which is what happened when the path was a
# bare /nix/store hash copied by hand.
#
# Usage:
#   nix-shell            # enter the shell, then ./start.sh
#   nix-shell --run ./start.sh
#   nix-shell --run './start.sh test'
#
# On macOS or a conventional Linux this file is ignored; nothing needs it.
{ pkgs ? import <nixpkgs> { } }:

pkgs.mkShell {
  # Python is provided so `python3 -m venv` works without a system Python.
  packages = [
    pkgs.python311
    pkgs.stdenv.cc.cc.lib   # libstdc++
    pkgs.zlib
    pkgs.portaudio          # sounddevice
    pkgs.ffmpeg             # whisper / audio decoding
  ];

  # mkShell points LD_LIBRARY_PATH at this closure, so the extensions resolve.
  # The venv's own bin/ is added by start.sh, not here.
  LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [
    pkgs.stdenv.cc.cc.lib
    pkgs.zlib
    pkgs.portaudio
    pkgs.ffmpeg
  ];
}
