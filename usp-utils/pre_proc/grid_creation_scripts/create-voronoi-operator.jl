#!/usr/bin/env -S julia --project=@cgfd-usp-mpas --threads=auto

using NCDatasets, Comonicon
using VoronoiOperators


VoronoiOperators.create_voronoi_operator(ARGS)
