#!/usr/bin/env julia

import Pkg
import Pkg: PackageSpec

#Packages to install
const pkgs = [
              PackageSpec("NCDatasets"),
              PackageSpec("DelaunayTriangulation"),
              PackageSpec("GLMakie"),
              PackageSpec("Comonicon"),
              PackageSpec(url="https://github.com/favba/TensorsLite.jl.git"),
              PackageSpec(url="https://github.com/CGFD-USP/TensorsLiteGeometry.jl.git"),
              PackageSpec(url="https://github.com/CGFD-USP/VoronoiMeshes.jl.git"),
              PackageSpec(url="https://github.com/CGFD-USP/VoronoiOperators.jl.git"),
              PackageSpec(url="https://github.com/CGFD-USP/MPASMeshes.jl.git")
             ]

Pkg.activate("cgfd-usp-mpas", shared=true)

Pkg.add(pkgs)

