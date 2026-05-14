{
  description = "Hanzi practice-worksheet generator (HSK 3.0 list + patched cwg)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        pythonEnv = pkgs.python3.withPackages (ps: with ps; [
          cairosvg
          reportlab
          pillow
        ]);
      in
      {
        devShells.default = pkgs.mkShell {
          packages = [
            pythonEnv
            pkgs.cairo
            pkgs.pango
            pkgs.git
            pkgs.curl
            pkgs.gnutar
            pkgs.gzip
            pkgs.p7zip
            pkgs.noto-fonts-cjk-sans
          ];

          shellHook = ''
            echo "hanzi_worksheets devshell — run ./setup.sh once, then python make_worksheet.py"
          '';
        };

        packages.default = pkgs.writeShellApplication {
          name = "hanzi-worksheet";
          runtimeInputs = [ pythonEnv pkgs.cairo ];
          text = ''
            exec ${pythonEnv}/bin/python ${./make_worksheet.py} "$@"
          '';
        };
      });
}
