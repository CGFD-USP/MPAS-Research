#!/usr/bin/env -S julia --project=@cgfd-usp-mpas --threads=auto

using NCDatasets, Comonicon
using VoronoiOperators

const ce = Base.get_extension(VoronoiOperators, :ComoniconExt)

ce.command_main(ARGS)
