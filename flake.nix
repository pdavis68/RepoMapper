{
  description = "RepoMapper (repomap CLI + MCP server)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = import nixpkgs { inherit system; };

        python = pkgs.python313;
        pythonEnv = python.withPackages (
          ps: with ps; [
            diskcache
            fastmcp
            grep-ast
            networkx
            pygments
            tiktoken
            tree-sitter
          ]
        );

        repomapper = pkgs.stdenvNoCC.mkDerivation {
          pname = "repomapper";
          version = "0.1.0";
          src = self;

          nativeBuildInputs = [ pkgs.makeWrapper ];
          dontBuild = true;

          installPhase = ''
            runHook preInstall

            appDir="$out/share/repomapper"
            mkdir -p "$appDir"

            cp -r \
              repomap.py \
              repomap_server.py \
              repomap_class.py \
              utils.py \
              importance.py \
              scm.py \
              queries \
              "$appDir/"

            mkdir -p "$out/bin"

            makeWrapper "${pythonEnv}/bin/python" "$out/bin/repomap" \
              --set PYTHONPATH "$appDir" \
              --add-flags "-m repomap"

            makeWrapper "${pythonEnv}/bin/python" "$out/bin/repomap-mcp" \
              --set PYTHONPATH "$appDir" \
              --add-flags "-m repomap_server"

            runHook postInstall
          '';

          meta = with pkgs.lib; {
            description = "RepoMap command-line tool and MCP server";
            license = licenses.mit;
            platforms = platforms.all;
            mainProgram = "repomap";
          };
        };
      in
      {
        packages = {
          inherit repomapper;
          default = repomapper;
        };

        apps = {
          repomap = flake-utils.lib.mkApp {
            drv = repomapper;
            exePath = "/bin/repomap";
          };

          repomap-mcp = flake-utils.lib.mkApp {
            drv = repomapper;
            exePath = "/bin/repomap-mcp";
          };

          default = flake-utils.lib.mkApp {
            drv = repomapper;
            exePath = "/bin/repomap";
          };
        };

        devShells.default = pkgs.mkShell {
          packages = [
            pythonEnv
          ];
        };
      }
    );
}
