#!/usr/bin/env julia
# Points the shared environment @cgfd-usp-mpas at local checkouts of its packages
# (Pkg.develop), e.g. those of <MPAS-Research>/external. Every package folder of
# <dir> that the environment uses is developed, the others are left alone. When
# the environment found is read-only (the MPAS image), it is first copied into
# the writable depot, which then takes precedence.
# Usage: julia develop_julia_packages.jl <dir>
# Undo: Pkg.free(<name>) in the environment, or delete the copy in the writable depot.

import Pkg

const name = "cgfd-usp-mpas"
dir = abspath(get(ARGS, 1, ""))
isdir(dir) || error("usage: julia develop_julia_packages.jl <dir>")

target = joinpath(first(DEPOT_PATH), "environments", name)
if !isfile(joinpath(target, "Project.toml"))
    src = findfirst(d -> isfile(joinpath(d, "environments", name, "Project.toml")), DEPOT_PATH)
    src === nothing && error("no environment @$name, install it with install_julia_environment.jl")
    mkpath(target)
    for f in ("Project.toml", "Manifest.toml")
        cp(joinpath(DEPOT_PATH[src], "environments", name, f), joinpath(target, f))
        chmod(joinpath(target, f), 0o644)
    end
end

Pkg.activate(target)
used = Set(p.name for p in values(Pkg.dependencies()))
paths = filter(readdir(dir; join=true)) do p
    project = joinpath(p, "Project.toml")
    isfile(project) && get(Pkg.TOML.parsefile(project), "name", "") in used
end
isempty(paths) && error("no package of @$name in $dir")
Pkg.develop([Pkg.PackageSpec(path=p) for p in paths])
Pkg.status()
