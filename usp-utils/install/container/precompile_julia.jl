# Image build step: precompiles the shared environment @cgfd-usp-mpas for the
# CPU targets of JULIA_CPU_TARGET. The packages installed from git (TensorsLite
# and the CGFD packages) compile at run time for the host CPU, since LLVM fails
# on their SIMD code for the generic target, so their caches are removed here.
using Pkg, TOML

Pkg.activate("cgfd-usp-mpas"; shared=true)
try
    Pkg.precompile()
catch
    println("precompile reported failures, checking the dependencies")
end

compiled = joinpath(DEPOT_PATH[1], "compiled", "v$(VERSION.major).$(VERSION.minor)")
for p in values(Pkg.dependencies())
    p.is_tracking_repo || continue
    exts = keys(get(TOML.parsefile(joinpath(p.source, "Project.toml")), "extensions", Dict()))
    for name in [p.name; collect(exts)]
        rm(joinpath(compiled, name); force=true, recursive=true)
    end
end

missing_pkgs = String[]
for (uuid, p) in Pkg.dependencies()
    p.is_tracking_repo && continue
    id = Base.PkgId(uuid, p.name)
    (Base.in_sysimage(id) || Base.locate_package(id) === nothing) && continue
    Base.isprecompiled(id) || push!(missing_pkgs, p.name)
end
isempty(missing_pkgs) || error("not precompiled: ", join(missing_pkgs, ", "))
println("all dependencies precompiled")
