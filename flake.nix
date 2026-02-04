# https://www.youtube.com/watch?v=6fftiTJ2vuQ
# nix-shell -p ninja pkg-config cairo libxcrypt --run "nix run github:nix-community/pip2nix -- generate flask bootstrap-flask flask-mail peewee dotenv xhtml2pdf qrcode"
{
  description = "python-nix";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs, ... }: # self is not being used but it is working
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
      packageOverrides = pkgs.callPackage ./python-packages.nix { };
      python = pkgs.python3.override { inherit packageOverrides; };
    in
    {
      devShells.x86_64-linux.default = pkgs.mkShell {
        packages = [
          (python.withPackages (p: [ p.flask p.bootstrap-flask p.dotenv p.peewee p.flask-mail p.xhtml2pdf p.qrcode /* Add here more packages*/ ]))
        ];
      };
    };
}
