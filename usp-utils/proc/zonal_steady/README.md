# Steady zonal flow benchmark

An isothermal solid-body zonal flow over a flat surface, an exact steady state of the equations
MPAS-Atmosphere solves (the shallow-atmosphere equations, since `CURVATURE` is not defined), in
the role case 2 of Williamson et al. (1992) plays for shallow-water models. Any departure from
the initial state is truncation error, so the test measures how the errors of the dynamical
core decrease with resolution. The model is dry, with no physics, and the namelist is the one of
the baroclinic wave benchmark ([`../jw_baroclinic_wave`](../jw_baroclinic_wave)), whose scripts it
reuses.

| file | does |
|---|---|
| `common.sh` | settings on top of `../jw_baroclinic_wave/common.sh`: init case, model top, output fields, mixing variants |
| `run_zonal.sh <root> <mesh>[-ncar] <levels> <config> <ranks> <duration> [nodiss] [nosmdiv] [dt=<f> \| step=<s>]` | one run through `../jw_baroclinic_wave/run_jw.sh`, in `<root>/<mesh>/<case>_L<levels>/<config>_np<ranks>/` |
| `check_zonal.py <root> [<root> ...] [--day D]` | `errors.csv` (errors of every run and output time against the initial and the exact state), the check of each initial state, and errors against resolution with observed orders |
| `smoke.sh [root]` | smoke test on the 480 km mesh, 1 day per run, about 1 min on 4 cores |

## The solution

With u = u0 cos(lat), v = w = 0 and T = T0, the shallow-atmosphere equations with constant g and
radius a are in balance when

    p(lat, z) = p_eq exp(-((a Omega u0 + u0^2 / 2) sin^2(lat) + g z) / (R T0)),

so that rho = p / (R T0) and theta = T0 (p0 / p)^(R / cp). On pressure surfaces the geopotential
is R T0 ln(p_eq / p) - (a Omega u0 + u0^2 / 2) sin^2(lat), as the height of case 2. The vertical
equation reduces to hydrostatic balance, and the vector-invariant horizontal equation balances the
Coriolis term, the kinetic energy gradient and the pressure gradient. The flow is barotropic and
the absolute vorticity 2 (Omega + u0 / a) sin(lat) increases monotonically with latitude, so the
state has no baroclinic or barotropic instability that amplifies the truncation errors.

Parameters (`config_init_case = 11`): u0 = 2 pi a / 12 days (38.61 m/s, as in case 2),
T0 = 300 K, p_eq = 1000 hPa (surface pressure at the equator, 805 hPa at the poles), model top
`config_ztop` (30 km here) with `config_nvertlevels` uniform levels.

## Initial state

- Pressure: in each column, the discrete hydrostatic balance of the solver's vertical momentum
  equation, rdzu (p(k) - p(k-1)) = -g (fzm rho(k) + fzp rho(k-1)), from the surface pressure of
  the solution, extrapolated from the two lowest levels as `init_atmosphere` does. The base state
  (the atmosphere at rest with p_eq at the surface) is in the same discrete balance, so p(k) / p(1)
  is the same in every column and the vertical truncation error does not enter the horizontal
  pressure gradient. The pressure differs from the exact one by that vertical error only.
- Normal velocity at an edge: the mean of the normal velocity over the dual edge, i.e. the
  difference of the stream function -a u0 sin(lat) between its vertices over `dvEdge`. The
  discrete divergence of u is therefore zero. It differs from the point value at the edge by a
  second-order amount (2.6e-3 u0 at 480 km), which `check_zonal.py` prints.
- w = 0, f = 2 Omega sin(lat) at edges and vertices, flat surface (zeta = z).

## Use

```bash
source usp-utils/machines/env.sh
export MPAS_BUILD=~/mpas-builds/consistency-analysis_<commit>_double   # a build of build_mpas.sh
bash usp-utils/proc/zonal_steady/smoke.sh          # $MPAS_DATA_ROOT/mpas_benchmarks/zonal_smoke_<time>
bash usp-utils/pre_proc/grid_creation_scripts/prepare_ncar_mesh.sh x1.40962 32
bash usp-utils/proc/zonal_steady/run_zonal.sh $MPAS_DATA_ROOT/zonal x1.40962 30 trsk 32 10_00:00:00
bash usp-utils/proc/zonal_steady/run_zonal.sh $MPAS_DATA_ROOT/zonal x1.40962 30 trsk 32 10_00:00:00 nodiss
bash usp-utils/install/container/run.sh python3 usp-utils/proc/zonal_steady/check_zonal.py $MPAS_DATA_ROOT/zonal
```

Runs of `run_jw.sh` (segments, chains of jobs, `submit.sh` on a cluster) work the same way.

## Choices

- Configurations, time step (450 s at 120 km, proportional to the spacing), Smagorinsky length,
  advection orders and divergence damping: those of the baroclinic wave benchmark.
- Variants (case folder `zonal[-nodiss][-nosmdiv][-dt<f> | -step<s>]`): `nodiss` turns off the
  explicit horizontal mixing (`config_horiz_mixing = '2d_fixed'` with zero viscosities), and
  `nosmdiv` the divergence damping of the acoustic steps (`config_smdiv = 0`), while the upwind
  part of the third-order advection stays.
  `dt=<f>` multiplies the time step by f, and `step=<s>` sets it to s seconds, e.g. for the
  initial tendency (the departure after one short step over its length), which is the
  truncation error of the discrete model on the initial state. Measure it with `nosmdiv`, since
  the divergence damping removes most of the divergent part of the u tendency within a 60 s
  step, so that with it the one-step rate depends on the step.
- Output: u, w, theta, rho and pressure once a day (`ZS_HISTORY_INTERVAL`), no 2D diagnostics.
  At 30 km and 30 levels one output takes 1.1 GB.
- Errors (`check_zonal.py`): l2 is the rms weighted by the volume of the cell, of the edge
  (dcEdge dvEdge / 2 times the layer depth) or of the w level, and max the maximum absolute error,
  in the units of the field. The surface pressure is extrapolated from the two lowest levels as in
  `init_atmosphere`. Against `init`, the errors are the departure from the initial (discrete
  steady) state. Against `exact` they also include the vertical truncation error of the initial
  pressure, which does not decrease with the horizontal spacing.
