# Image build step: precompiles the shared environment @cgfd-usp-mpas for the
# CPU targets of JULIA_CPU_TARGET, so that different x86-64 machines load the
# same caches. Two kinds of packages compile at run time on each CPU instead,
# and their caches, with those of every package depending on them, are removed
# here: the packages installed from git (TensorsLite and the CGFD packages),
# since LLVM fails on their SIMD code for the generic target, and the packages
# that pick instructions from the CPU they are compiled on, whose image cache
# would carry the build machine's instructions to older CPUs.
using Pkg, TOML

# chooses its x86 code paths (BMI, AVX-512) with CpuId at precompile time
const host_specific = ["SmallCollections"]

Pkg.activate("cgfd-usp-mpas"; shared=true)
try
    Pkg.precompile()
catch
    println("precompile reported failures, checking the dependencies")
end

deps = Pkg.dependencies()
runtime = Set(p.name for p in values(deps) if p.is_tracking_repo || p.name in host_specific)
grown = true
while grown
    global grown = false
    for p in values(deps)
        if p.name ∉ runtime && any(in(runtime), keys(p.dependencies))
            push!(runtime, p.name)
            grown = true
        end
    end
end

compiled = joinpath(DEPOT_PATH[1], "compiled", "v$(VERSION.major).$(VERSION.minor)")
for p in values(deps)
    p.name in runtime || continue
    exts = keys(get(TOML.parsefile(joinpath(p.source, "Project.toml")), "extensions", Dict()))
    for name in [p.name; collect(exts)]
        rm(joinpath(compiled, name); force=true, recursive=true)
    end
end
println("compiled at run time: ", join(sort(collect(runtime)), ", "))

missing_pkgs = String[]
for (uuid, p) in deps
    p.name in runtime && continue
    id = Base.PkgId(uuid, p.name)
    (Base.in_sysimage(id) || Base.locate_package(id) === nothing) && continue
    Base.isprecompiled(id) || push!(missing_pkgs, p.name)
end
isempty(missing_pkgs) || error("not precompiled: ", join(missing_pkgs, ", "))
println("all other dependencies precompiled")
