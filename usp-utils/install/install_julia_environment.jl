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

# Packages named in CGFD_JULIA_SKIP (comma separated) are left out, e.g. GLMakie without a display
const skip = split(get(ENV, "CGFD_JULIA_SKIP", ""), ',', keepempty=false)

Pkg.activate("cgfd-usp-mpas", shared=true)

Pkg.add(filter(p -> p.name ∉ skip, pkgs))

