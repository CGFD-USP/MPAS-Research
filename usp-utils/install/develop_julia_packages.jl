#!/usr/bin/env julia
# Points the shared environment @cgfd-usp-mpas at local checkouts of its packages
# (Pkg.develop), e.g. those of <MPAS-Research>/external. Every package folder of
# <dir> that the environment uses is developed, the others are left alone. When
# a later depot holds the environment (the read-only one of the MPAS image), it
# is copied afresh into the writable depot first, so the copy follows the image
# after a rebuild, and the writable depot then takes precedence.
# Usage: julia develop_julia_packages.jl <dir>
# Undo: Pkg.free(<name>) in the environment, or delete the copy in the writable depot.

import Pkg

const name = "cgfd-usp-mpas"
dir = abspath(get(ARGS, 1, ""))
isdir(dir) || error("usage: julia develop_julia_packages.jl <dir>")

target = joinpath(first(DEPOT_PATH), "environments", name)
image = findfirst(d -> isfile(joinpath(d, "environments", name, "Project.toml")), DEPOT_PATH[2:end])
if image !== nothing
    mkpath(target)
    for f in ("Project.toml", "Manifest.toml")
        cp(joinpath(DEPOT_PATH[image + 1], "environments", name, f), joinpath(target, f); force=true)
        chmod(joinpath(target, f), 0o644)
    end
elseif !isfile(joinpath(target, "Project.toml"))
    error("no environment @$name, install it with install_julia_environment.jl")
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
