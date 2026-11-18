#!/usr/bin/env -S julia --project=@cgfd-usp-mpas --threads=auto

using NCDatasets, Comonicon
using MPASMeshes

MPASMeshes.regenerate_mesh(ARGS)
