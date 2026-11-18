! Copyright (c) 2026, Universidade de São Paulo
!
! Unless noted otherwise source code is licensed under the BSD license.
! Additional copyright and license information can be found in the LICENSE file
! distributed with this code, or at http://mpas-dev.github.com/license.html
!
!-----------------------------------------------------------------------
!  module mpas_atm_consistent_operators
!
!> \brief Velocity reconstructions consistent with the Voronoi mesh geometry
!> \author Pedro Peixoto
!> \date   17 November 2026
!> \details
!>  Weights computed once at start-up from the positions of the cell generators
!>  and of the Voronoi vertices:
!>   - config_ke_reconstruction: the velocity vector at cells and vertices from the
!>     normal velocities of their edges, by the reconstruction of Perot ('perot') or
!>     by a least-squares fit of a linear vector field ('lsq2'). The cell weights
!>     replace the coefficients coeffs_reconstruct of mpas_vector_reconstruction, the
!>     vertex weights go to coeffs_reconstruct_vertex.
!>   - config_cell_wind_reconstruction = 'perot' or 'lsq2' with config_ke_reconstruction
!>     = 'trsk': the same cell weights in coeffs_reconstruct, so only the cell velocity
!>     of the physics and the output changes.
!>   - config_tangential_reconstruction = 'perot': the tangential velocity of an
!>     edge as the mean of the Perot velocities of its two cells along the edge,
!>     on the stencil nEdgesOnEdge_perot, edgesOnEdge_perot (its edgesOnEdge, then
!>     the edge itself) with the weights weightsOnEdge_perot.
!>   - config_edge_midpoint_flux: the normal flux at the midpoint of the Voronoi
!>     edge from the fluxes at the edge points x_t of the edge and of its
!>     edgesOnEdge, by a least-squares fit of a linear vector field (weights
!>     coeffs_edge_midpoint_own and coeffs_edge_midpoint). The module also holds
!>     the per-stage kernels of this option: the edge fluxes of the large step
!>     (atm_compute_edge_fluxes, then atm_compute_midpoint_fluxes after their halo
!>     exchange) and the matching mass flux of the scalar transport
!>     (atm_edge_midpoint_ruavg).
!>
!>  Positions are taken on the unit sphere and projected (gnomonic projection)
!>  onto the plane tangent at the cell, vertex or edge. A weight is computed only
!>  where all its inputs are in the block; elsewhere the cell keeps the
!>  coefficients of mpas_init_reconstruct, the vertex gets zero weights, the edge
!>  the stencil and weights of MPAS (edgesOnEdge, weightsOnEdge), and the midpoint
!>  flux is the flux at x_t.
!
!-----------------------------------------------------------------------
module mpas_atm_consistent_operators

   use mpas_kind_types, only : RKIND, R8KIND, StrKIND
   use mpas_derived_types, only : mpas_pool_type, MPAS_LOG_CRIT
   use mpas_pool_routines, only : mpas_pool_get_array, mpas_pool_get_dimension, mpas_pool_get_config
   use mpas_log, only : mpas_log_write
   use mpas_timer, only : mpas_timer_start, mpas_timer_stop
   use mpas_atm_dimensions, only : nVertLevels

   implicit none

   private
   public :: atm_consistent_operators_init, atm_compute_edge_fluxes, atm_compute_midpoint_fluxes, atm_edge_midpoint_ruavg

   ! Unknowns of the least-squares fit of a linear vector field (a, b) + G x, with components a, b along the
   ! basis vectors e1, e2 and offsets x along them: a, b, da/dx1, db/dx1, da/dx2, db/dx2
   integer, parameter :: fit_a = 1, fit_b = 2, fit_dadx1 = 3, fit_dbdx1 = 4, fit_dadx2 = 5, fit_dbdx2 = 6
   integer, parameter :: nfit = 6

   ! A fit whose normal matrix has a larger condition number gets its gradient terms
   ! regularized by the norm of that matrix divided by this number
   real (kind=R8KIND), parameter :: lsq_max_condition = 5.0e6_R8KIND

   ! Largest number of sweeps of the Jacobi eigenvalue iteration (it converges in a few)
   integer, parameter :: max_jacobi_sweeps = 50

   ! Largest | |x| / sphere_radius - 1 | of a cell or vertex position x: 1e-10, or four roundoffs of the
   ! working precision where that is larger (single precision)
   real (kind=R8KIND), parameter :: unit_norm_tolerance = max(1.0e-10_R8KIND, 4.0_R8KIND * epsilon(1.0_RKIND))


   contains


   !-----------------------------------------------------------------------
   !  routine atm_consistent_operators_init
   !
   !> \brief Computes the weights of the selected options
   !> \author Pedro Peixoto
   !> \date   17 November 2026
   !> \details
   !>  Called once per block at start-up, after mpas_init_reconstruct and before
   !>  the first diagnostics. Does nothing with the default options. Computes the
   !>  geometry shared by the options, then the weights of each option in
   !>  init_cell_weights, init_vertex_weights, init_tangential_weights and
   !>  init_midpoint_weights.
   !
   !-----------------------------------------------------------------------
   subroutine atm_consistent_operators_init(mesh, configs)

      implicit none

      type (mpas_pool_type), intent(inout) :: mesh
      type (mpas_pool_type), intent(in) :: configs

      character (len=StrKIND), pointer :: config_ke_reconstruction, config_tangential_reconstruction, &
                                          config_cell_wind_reconstruction
      logical, pointer :: config_edge_midpoint_flux
      logical, pointer :: on_a_sphere
      real (kind=RKIND), pointer :: sphere_radius
      integer, pointer :: nCells, nEdges, nVertices, maxEdges
      integer, dimension(:), pointer :: nEdgesOnCell
      integer, dimension(:,:), pointer :: edgesOnCell, verticesOnCell, verticesOnEdge, cellsOnEdge
      real (kind=RKIND), dimension(:), pointer :: xCell, yCell, zCell, xVertex, yVertex, zVertex
      real (kind=RKIND), dimension(:,:), pointer :: edgesOnCell_sign

      real (kind=R8KIND), dimension(:,:), allocatable :: xc, xv, xt, ne
      real (kind=R8KIND), dimension(:,:,:), allocatable :: wperot
      logical, dimension(:), allocatable :: edge_ok, perot_ok
      real (kind=R8KIND) :: r
      logical :: ke_perot, ke_lsq2, cell_perot, cell_lsq2, tangential_perot
      integer :: iCell, iEdge, iVertex, n

      call mpas_pool_get_config(configs, 'config_ke_reconstruction', config_ke_reconstruction)
      call mpas_pool_get_config(configs, 'config_cell_wind_reconstruction', config_cell_wind_reconstruction)
      call mpas_pool_get_config(configs, 'config_tangential_reconstruction', config_tangential_reconstruction)
      call mpas_pool_get_config(configs, 'config_edge_midpoint_flux', config_edge_midpoint_flux)
      ke_perot = trim(config_ke_reconstruction) == 'perot'
      ke_lsq2 = trim(config_ke_reconstruction) == 'lsq2'
      ! mpas_atm_dynamics_checks allows at most one of the two
      cell_perot = ke_perot .or. trim(config_cell_wind_reconstruction) == 'perot'
      cell_lsq2 = ke_lsq2 .or. trim(config_cell_wind_reconstruction) == 'lsq2'
      tangential_perot = trim(config_tangential_reconstruction) == 'perot'
      if (.not. (cell_perot .or. cell_lsq2 .or. tangential_perot .or. config_edge_midpoint_flux)) return

      call mpas_timer_start('atm_consistent_operators_init')

      call mpas_pool_get_config(mesh, 'on_a_sphere', on_a_sphere)
      if (.not. on_a_sphere) then
         call mpas_log_write('config_ke_reconstruction, config_cell_wind_reconstruction, config_tangential_reconstruction'// &
                             ' and config_edge_midpoint_flux need a spherical mesh', messageType=MPAS_LOG_CRIT)
      end if
      call mpas_pool_get_config(mesh, 'sphere_radius', sphere_radius)

      call mpas_pool_get_dimension(mesh, 'nCells', nCells)
      call mpas_pool_get_dimension(mesh, 'nEdges', nEdges)
      call mpas_pool_get_dimension(mesh, 'nVertices', nVertices)
      call mpas_pool_get_dimension(mesh, 'maxEdges', maxEdges)

      call mpas_pool_get_array(mesh, 'xCell', xCell)
      call mpas_pool_get_array(mesh, 'yCell', yCell)
      call mpas_pool_get_array(mesh, 'zCell', zCell)
      call mpas_pool_get_array(mesh, 'xVertex', xVertex)
      call mpas_pool_get_array(mesh, 'yVertex', yVertex)
      call mpas_pool_get_array(mesh, 'zVertex', zVertex)
      call mpas_pool_get_array(mesh, 'nEdgesOnCell', nEdgesOnCell)
      call mpas_pool_get_array(mesh, 'edgesOnCell', edgesOnCell)
      call mpas_pool_get_array(mesh, 'verticesOnCell', verticesOnCell)
      call mpas_pool_get_array(mesh, 'verticesOnEdge', verticesOnEdge)
      call mpas_pool_get_array(mesh, 'cellsOnEdge', cellsOnEdge)
      call mpas_pool_get_array(mesh, 'edgesOnCell_sign', edgesOnCell_sign)

      ! positions on the unit sphere
      r = 1.0_R8KIND / real(sphere_radius, R8KIND)
      allocate(xc(3,nCells), xv(3,nVertices))
      do iCell = 1, nCells
         xc(:,iCell) = (/ real(xCell(iCell), R8KIND), real(yCell(iCell), R8KIND), real(zCell(iCell), R8KIND) /) * r
      end do
      do iVertex = 1, nVertices
         xv(:,iVertex) = (/ real(xVertex(iVertex), R8KIND), real(yVertex(iVertex), R8KIND), real(zVertex(iVertex), R8KIND) /) * r
      end do
      call check_unit_norm('xCell, yCell, zCell', xc, sphere_radius)
      call check_unit_norm('xVertex, yVertex, zVertex', xv, sphere_radius)

      ! edges whose two cells are in the block: point x_t (midpoint of the arc between the cells) and unit normal
      allocate(xt(3,nEdges), ne(3,nEdges), edge_ok(nEdges))
      do iEdge = 1, nEdges
         edge_ok(iEdge) = all(cellsOnEdge(:,iEdge) >= 1 .and. cellsOnEdge(:,iEdge) <= nCells)
         if (edge_ok(iEdge)) then
            xt(:,iEdge) = unit(xc(:,cellsOnEdge(1,iEdge)) + xc(:,cellsOnEdge(2,iEdge)))
            ne(:,iEdge) = unit(xc(:,cellsOnEdge(2,iEdge)) - xc(:,cellsOnEdge(1,iEdge)))
         end if
      end do

      ! Perot velocity of the cells whose edges and vertices are in the block
      allocate(perot_ok(nCells))
      do iCell = 1, nCells
         n = nEdgesOnCell(iCell)
         perot_ok(iCell) = all(edgesOnCell(1:n,iCell) >= 1 .and. edgesOnCell(1:n,iCell) <= nEdges) .and. &
                           all(verticesOnCell(1:n,iCell) >= 1 .and. verticesOnCell(1:n,iCell) <= nVertices)
      end do
      if (cell_perot .or. tangential_perot) then
         allocate(wperot(3,maxEdges,nCells))
         do iCell = 1, nCells
            if (perot_ok(iCell)) then
               call perot_cell_weights(xc(:,iCell), nEdgesOnCell(iCell), edgesOnCell(:,iCell), verticesOnCell(:,iCell), &
                                       edgesOnCell_sign(:,iCell), verticesOnEdge, xv, wperot(:,:,iCell))
            end if
         end do
      end if

      if (cell_perot .or. cell_lsq2) call init_cell_weights(mesh, cell_perot, xc, xt, ne, edge_ok, perot_ok, wperot)
      if (ke_perot .or. ke_lsq2) call init_vertex_weights(mesh, ke_perot, xc, xv, xt, ne, edge_ok)
      if (tangential_perot) call init_tangential_weights(mesh, xc, xv, ne, edge_ok, perot_ok, wperot)
      if (config_edge_midpoint_flux) call init_midpoint_weights(mesh, xc, xv, xt, ne, edge_ok)

      if (allocated(wperot)) deallocate(wperot)
      deallocate(xc, xv, xt, ne, edge_ok, perot_ok)

      call mpas_timer_stop('atm_consistent_operators_init')

   end subroutine atm_consistent_operators_init


   !-----------------------------------------------------------------------
   !  routine init_cell_weights
   !
   !> \brief Cell velocity from the Perot or lsq2 weights
   !> \author Pedro Peixoto
   !> \date   17 November 2026
   !> \details
   !>  Replaces coeffs_reconstruct on the cells whose stencil is in the block,
   !>  where wperot holds the Perot weights if perot; the other cells keep the
   !>  coefficients of mpas_init_reconstruct.
   !
   !-----------------------------------------------------------------------
   subroutine init_cell_weights(mesh, perot, xc, xt, ne, edge_ok, perot_ok, wperot)

      implicit none

      type (mpas_pool_type), intent(inout) :: mesh
      logical, intent(in) :: perot
      real (kind=R8KIND), dimension(:,:), intent(in) :: xc, xt, ne
      logical, dimension(:), intent(in) :: edge_ok, perot_ok
      real (kind=R8KIND), dimension(:,:,:), allocatable, intent(in) :: wperot

      integer, pointer :: nCells, nCellsSolve, maxEdges
      integer, dimension(:), pointer :: nEdgesOnCell
      integer, dimension(:,:), pointer :: edgesOnCell
      real (kind=RKIND), dimension(:,:,:), pointer :: coeffs_reconstruct

      real (kind=R8KIND), dimension(:,:), allocatable :: wc
      character (len=5) :: method
      logical :: cell_ok
      integer :: iCell, n, nFallback

      call mpas_pool_get_dimension(mesh, 'nCells', nCells)
      call mpas_pool_get_dimension(mesh, 'nCellsSolve', nCellsSolve)
      call mpas_pool_get_dimension(mesh, 'maxEdges', maxEdges)
      call mpas_pool_get_array(mesh, 'nEdgesOnCell', nEdgesOnCell)
      call mpas_pool_get_array(mesh, 'edgesOnCell', edgesOnCell)
      call mpas_pool_get_array(mesh, 'coeffs_reconstruct', coeffs_reconstruct)

      allocate(wc(3,maxEdges))
      nFallback = 0
      do iCell = 1, nCells
         n = nEdgesOnCell(iCell)
         cell_ok = perot_ok(iCell)
         if (cell_ok .and. .not. perot) cell_ok = all(edge_ok(edgesOnCell(1:n,iCell)))
         if (.not. cell_ok) then
            if (iCell <= nCellsSolve) nFallback = nFallback + 1
            cycle
         end if
         if (perot) then
            wc(:,1:n) = wperot(:,1:n,iCell)
         else
            call lsq2_vector_weights(xc(:,iCell), n, edgesOnCell(:,iCell), xt, ne, wc)
         end if
         coeffs_reconstruct(:,:,iCell) = 0.0_RKIND
         coeffs_reconstruct(:,1:n,iCell) = real(wc(:,1:n), RKIND)
      end do
      deallocate(wc)

      method = 'lsq2'
      if (perot) method = 'perot'
      call mpas_log_write('Cell velocity from the '//trim(method)//' reconstruction; owned cells without it: $i', &
                          intArgs=(/nFallback/))

   end subroutine init_cell_weights


   !-----------------------------------------------------------------------
   !  routine init_vertex_weights
   !
   !> \brief Vertex velocity of the kinetic energy from the Perot or lsq2 weights
   !> \author Pedro Peixoto
   !> \date   17 November 2026
   !> \details
   !>  coeffs_reconstruct_vertex on the vertices whose stencil is in the block,
   !>  zero weights on the others.
   !
   !-----------------------------------------------------------------------
   subroutine init_vertex_weights(mesh, perot, xc, xv, xt, ne, edge_ok)

      implicit none

      type (mpas_pool_type), intent(inout) :: mesh
      logical, intent(in) :: perot
      real (kind=R8KIND), dimension(:,:), intent(in) :: xc, xv, xt, ne
      logical, dimension(:), intent(in) :: edge_ok

      integer, pointer :: nCells, nEdges, nVertices, nVerticesSolve, vertexDegree
      integer, dimension(:,:), pointer :: edgesOnVertex, cellsOnVertex, cellsOnEdge
      real (kind=RKIND), dimension(:,:,:), pointer :: coeffs_reconstruct_vertex

      real (kind=R8KIND), dimension(:,:), allocatable :: wv
      character (len=5) :: method
      logical :: vertex_ok
      integer :: iVertex, nFallback

      call mpas_pool_get_dimension(mesh, 'nCells', nCells)
      call mpas_pool_get_dimension(mesh, 'nEdges', nEdges)
      call mpas_pool_get_dimension(mesh, 'nVertices', nVertices)
      call mpas_pool_get_dimension(mesh, 'nVerticesSolve', nVerticesSolve)
      call mpas_pool_get_dimension(mesh, 'vertexDegree', vertexDegree)
      call mpas_pool_get_array(mesh, 'edgesOnVertex', edgesOnVertex)
      call mpas_pool_get_array(mesh, 'cellsOnVertex', cellsOnVertex)
      call mpas_pool_get_array(mesh, 'cellsOnEdge', cellsOnEdge)
      call mpas_pool_get_array(mesh, 'coeffs_reconstruct_vertex', coeffs_reconstruct_vertex)

      allocate(wv(3,vertexDegree))
      nFallback = 0
      do iVertex = 1, nVertices
         coeffs_reconstruct_vertex(:,:,iVertex) = 0.0_RKIND
         vertex_ok = all(edgesOnVertex(:,iVertex) >= 1 .and. edgesOnVertex(:,iVertex) <= nEdges) .and. &
                     all(cellsOnVertex(:,iVertex) >= 1 .and. cellsOnVertex(:,iVertex) <= nCells)
         if (vertex_ok) vertex_ok = all(edge_ok(edgesOnVertex(:,iVertex)))
         if (.not. vertex_ok) then
            if (iVertex <= nVerticesSolve) nFallback = nFallback + 1
            cycle
         end if
         if (perot) then
            call perot_vertex_weights(xv(:,iVertex), vertexDegree, edgesOnVertex(:,iVertex), cellsOnVertex(:,iVertex), &
                                      cellsOnEdge, xc, ne, wv)
         else
            call lsq2_vector_weights(xv(:,iVertex), vertexDegree, edgesOnVertex(:,iVertex), xt, ne, wv)
         end if
         coeffs_reconstruct_vertex(:,:,iVertex) = real(wv, RKIND)
      end do
      deallocate(wv)

      method = 'lsq2'
      if (perot) method = 'perot'
      call mpas_log_write('Kinetic energy and cell velocity from the '//trim(method)//' reconstruction;'// &
                          ' owned vertices without it: $i', intArgs=(/nFallback/))

   end subroutine init_vertex_weights


   !-----------------------------------------------------------------------
   !  routine init_tangential_weights
   !
   !> \brief Tangential velocity of the edges from the Perot velocities of their cells
   !> \author Pedro Peixoto
   !> \date   17 November 2026
   !> \details
   !>  On the edges whose two cells have Perot weights in wperot, the stencil
   !>  nEdgesOnEdge_perot, edgesOnEdge_perot is the edgesOnEdge of the edge, then
   !>  the edge itself, with the weights weightsOnEdge_perot; the other edges get
   !>  the stencil and weights of MPAS.
   !
   !-----------------------------------------------------------------------
   subroutine init_tangential_weights(mesh, xc, xv, ne, edge_ok, perot_ok, wperot)

      implicit none

      type (mpas_pool_type), intent(inout) :: mesh
      real (kind=R8KIND), dimension(:,:), intent(in) :: xc, xv, ne
      logical, dimension(:), intent(in) :: edge_ok, perot_ok
      real (kind=R8KIND), dimension(:,:,:), intent(in) :: wperot

      integer, pointer :: nEdges, nEdgesSolve
      integer, dimension(:), pointer :: nEdgesOnCell, nEdgesOnEdge, nEdgesOnEdge_perot
      integer, dimension(:,:), pointer :: edgesOnCell, edgesOnEdge, edgesOnEdge_perot, cellsOnEdge, verticesOnEdge
      real (kind=RKIND), dimension(:,:), pointer :: weightsOnEdge, weightsOnEdge_perot

      real (kind=R8KIND), dimension(:), allocatable :: we
      integer :: iEdge, c1, c2, n, nFallback

      call mpas_pool_get_dimension(mesh, 'nEdges', nEdges)
      call mpas_pool_get_dimension(mesh, 'nEdgesSolve', nEdgesSolve)
      call mpas_pool_get_array(mesh, 'nEdgesOnCell', nEdgesOnCell)
      call mpas_pool_get_array(mesh, 'edgesOnCell', edgesOnCell)
      call mpas_pool_get_array(mesh, 'nEdgesOnEdge', nEdgesOnEdge)
      call mpas_pool_get_array(mesh, 'edgesOnEdge', edgesOnEdge)
      call mpas_pool_get_array(mesh, 'cellsOnEdge', cellsOnEdge)
      call mpas_pool_get_array(mesh, 'verticesOnEdge', verticesOnEdge)
      call mpas_pool_get_array(mesh, 'weightsOnEdge', weightsOnEdge)
      call mpas_pool_get_array(mesh, 'nEdgesOnEdge_perot', nEdgesOnEdge_perot)
      call mpas_pool_get_array(mesh, 'edgesOnEdge_perot', edgesOnEdge_perot)
      call mpas_pool_get_array(mesh, 'weightsOnEdge_perot', weightsOnEdge_perot)

      ! leading dimension maxEdges2P1 of the stencil arrays: slot n+1 is free for the edge itself
      allocate(we(size(weightsOnEdge_perot,1)))
      nFallback = 0
      do iEdge = 1, nEdges
         n = nEdgesOnEdge(iEdge)
         edgesOnEdge_perot(:,iEdge) = 0
         edgesOnEdge_perot(1:n,iEdge) = edgesOnEdge(1:n,iEdge)
         if (edge_ok(iEdge)) then
            c1 = cellsOnEdge(1,iEdge)
            c2 = cellsOnEdge(2,iEdge)
            if (perot_ok(c1) .and. perot_ok(c2)) then
               call perot_tangential_weights(iEdge, n, edgesOnEdge(:,iEdge), cellsOnEdge(:,iEdge), verticesOnEdge(:,iEdge), &
                                             xc, xv, ne(:,iEdge), nEdgesOnCell, edgesOnCell, wperot, we)
               nEdgesOnEdge_perot(iEdge) = n + 1
               edgesOnEdge_perot(n+1,iEdge) = iEdge
               weightsOnEdge_perot(:,iEdge) = real(we, RKIND)
               cycle
            end if
         end if
         nEdgesOnEdge_perot(iEdge) = n
         weightsOnEdge_perot(:,iEdge) = 0.0_RKIND
         weightsOnEdge_perot(1:n,iEdge) = weightsOnEdge(1:n,iEdge)
         if (iEdge <= nEdgesSolve) nFallback = nFallback + 1
      end do
      deallocate(we)

      call mpas_log_write('Tangential velocity from the Perot velocities of the cells; owned edges without it: $i', &
                          intArgs=(/nFallback/))

   end subroutine init_tangential_weights


   !-----------------------------------------------------------------------
   !  routine init_midpoint_weights
   !
   !> \brief Weights of the flux at the Voronoi edge midpoint
   !> \author Pedro Peixoto
   !> \date   17 November 2026
   !> \details
   !>  coeffs_edge_midpoint and coeffs_edge_midpoint_own on the edges whose stencil
   !>  is in the block; on the others the midpoint flux is the flux at x_t.
   !
   !-----------------------------------------------------------------------
   subroutine init_midpoint_weights(mesh, xc, xv, xt, ne, edge_ok)

      implicit none

      type (mpas_pool_type), intent(inout) :: mesh
      real (kind=R8KIND), dimension(:,:), intent(in) :: xc, xv, xt, ne
      logical, dimension(:), intent(in) :: edge_ok

      integer, pointer :: nEdges, nVertices, nEdgesSolve
      integer, dimension(:), pointer :: nEdgesOnEdge
      integer, dimension(:,:), pointer :: edgesOnEdge, cellsOnEdge, verticesOnEdge
      real (kind=RKIND), dimension(:,:), pointer :: coeffs_edge_midpoint
      real (kind=RKIND), dimension(:), pointer :: coeffs_edge_midpoint_own

      real (kind=R8KIND), dimension(:), allocatable :: we
      real (kind=R8KIND) :: wown
      integer :: iEdge, nFallback

      call mpas_pool_get_dimension(mesh, 'nEdges', nEdges)
      call mpas_pool_get_dimension(mesh, 'nVertices', nVertices)
      call mpas_pool_get_dimension(mesh, 'nEdgesSolve', nEdgesSolve)
      call mpas_pool_get_array(mesh, 'nEdgesOnEdge', nEdgesOnEdge)
      call mpas_pool_get_array(mesh, 'edgesOnEdge', edgesOnEdge)
      call mpas_pool_get_array(mesh, 'cellsOnEdge', cellsOnEdge)
      call mpas_pool_get_array(mesh, 'verticesOnEdge', verticesOnEdge)
      call mpas_pool_get_array(mesh, 'coeffs_edge_midpoint', coeffs_edge_midpoint)
      call mpas_pool_get_array(mesh, 'coeffs_edge_midpoint_own', coeffs_edge_midpoint_own)

      allocate(we(size(coeffs_edge_midpoint,1)))
      nFallback = 0
      do iEdge = 1, nEdges
         if (midpoint_stencil_ok(iEdge, nEdgesOnEdge(iEdge), edgesOnEdge(:,iEdge), verticesOnEdge(:,iEdge), &
                                 nEdges, nVertices, edge_ok)) then
            call edge_midpoint_weights(iEdge, nEdgesOnEdge(iEdge), edgesOnEdge(:,iEdge), cellsOnEdge(:,iEdge), &
                                       verticesOnEdge(:,iEdge), xc, xv, xt, ne, we, wown)
            coeffs_edge_midpoint(:,iEdge) = real(we, RKIND)
            coeffs_edge_midpoint_own(iEdge) = real(wown, RKIND)
         else
            coeffs_edge_midpoint(:,iEdge) = 0.0_RKIND
            coeffs_edge_midpoint_own(iEdge) = 1.0_RKIND
            if (iEdge <= nEdgesSolve) nFallback = nFallback + 1
         end if
      end do
      deallocate(we)

      call mpas_log_write('Edge fluxes at the Voronoi edge midpoints; owned edges without the weights: $i', &
                          intArgs=(/nFallback/))

   end subroutine init_midpoint_weights


   !-----------------------------------------------------------------------
   !  routine atm_compute_edge_fluxes
   !
   !> \brief Edge fluxes of the large step with config_edge_midpoint_flux
   !> \author Pedro Peixoto
   !> \date   17 November 2026
   !> \details
   !>  On the edges edgeStart:edgeEnd, the horizontal fluxes per unit length of
   !>  theta_m (with the perturbation flux of RK stages 2 and 3) and of w at x_t,
   !>  as in the advection of atm_compute_dyn_tend, and the mass flux ru at the
   !>  Voronoi edge midpoint. The caller exchanges 'dynamics:edge_fluxes', after
   !>  which all three are valid on the edges of the owned and first-halo cells,
   !>  and then calls atm_compute_midpoint_fluxes.
   !
   !-----------------------------------------------------------------------
   subroutine atm_compute_edge_fluxes(state, diag, mesh, rk_step, edgeStart, edgeEnd)

      implicit none

      type (mpas_pool_type), intent(in) :: state
      type (mpas_pool_type), intent(inout) :: diag
      type (mpas_pool_type), intent(in) :: mesh
      integer, intent(in) :: rk_step, edgeStart, edgeEnd

      integer, pointer :: nCells, nEdges
      integer, dimension(:), pointer :: nAdvCellsForEdge, nEdgesOnEdge
      integer, dimension(:,:), pointer :: cellsOnEdge, advCellsForEdge, edgesOnEdge
      real (kind=RKIND), dimension(:), pointer :: invDvEdge, fzm, fzp, coeffs_edge_midpoint_own
      real (kind=RKIND), dimension(:,:), pointer :: adv_coefs, adv_coefs_3rd, coeffs_edge_midpoint, ru, ru_save, &
                                                    theta_m, theta_m_save, w, flux_theta_edge, flux_w_edge, ru_midpoint

      call mpas_pool_get_dimension(mesh, 'nCells', nCells)
      call mpas_pool_get_dimension(mesh, 'nEdges', nEdges)
      call mpas_pool_get_array(mesh, 'cellsOnEdge', cellsOnEdge)
      call mpas_pool_get_array(mesh, 'nAdvCellsForEdge', nAdvCellsForEdge)
      call mpas_pool_get_array(mesh, 'advCellsForEdge', advCellsForEdge)
      call mpas_pool_get_array(mesh, 'adv_coefs', adv_coefs)
      call mpas_pool_get_array(mesh, 'adv_coefs_3rd', adv_coefs_3rd)
      call mpas_pool_get_array(mesh, 'invDvEdge', invDvEdge)
      call mpas_pool_get_array(mesh, 'fzm', fzm)
      call mpas_pool_get_array(mesh, 'fzp', fzp)
      call mpas_pool_get_array(mesh, 'nEdgesOnEdge', nEdgesOnEdge)
      call mpas_pool_get_array(mesh, 'edgesOnEdge', edgesOnEdge)
      call mpas_pool_get_array(mesh, 'coeffs_edge_midpoint', coeffs_edge_midpoint)
      call mpas_pool_get_array(mesh, 'coeffs_edge_midpoint_own', coeffs_edge_midpoint_own)
      call mpas_pool_get_array(diag, 'ru', ru)
      call mpas_pool_get_array(diag, 'ru_save', ru_save)
      call mpas_pool_get_array(state, 'theta_m', theta_m, 2)
      call mpas_pool_get_array(state, 'theta_m', theta_m_save, 1)
      call mpas_pool_get_array(state, 'w', w, 2)
      call mpas_pool_get_array(diag, 'flux_theta_edge', flux_theta_edge)
      call mpas_pool_get_array(diag, 'flux_w_edge', flux_w_edge)
      call mpas_pool_get_array(diag, 'ru_midpoint', ru_midpoint)

      call atm_compute_edge_fluxes_work(nCells, nEdges, rk_step, cellsOnEdge, nAdvCellsForEdge, advCellsForEdge, &
                                        adv_coefs, adv_coefs_3rd, invDvEdge, fzm, fzp, nEdgesOnEdge, edgesOnEdge, &
                                        coeffs_edge_midpoint, coeffs_edge_midpoint_own, ru, ru_save, theta_m, theta_m_save, &
                                        w, flux_theta_edge, flux_w_edge, ru_midpoint, edgeStart, edgeEnd)

   end subroutine atm_compute_edge_fluxes


   subroutine atm_compute_edge_fluxes_work(nCells, nEdges, rk_step, cellsOnEdge, nAdvCellsForEdge, advCellsForEdge, &
                                           adv_coefs, adv_coefs_3rd, invDvEdge, fzm, fzp, nEdgesOnEdge, edgesOnEdge, &
                                           coeffs_edge_midpoint, coeffs_edge_midpoint_own, ru, ru_save, theta_m, theta_m_save, &
                                           w, flux_theta_edge, flux_w_edge, ru_midpoint, edgeStart, edgeEnd)

      implicit none

      integer, intent(in) :: nCells, nEdges, rk_step, edgeStart, edgeEnd
      integer, dimension(2,nEdges+1), intent(in) :: cellsOnEdge
      integer, dimension(nEdges+1), intent(in) :: nAdvCellsForEdge, nEdgesOnEdge
      integer, dimension(:,:), intent(in) :: advCellsForEdge, edgesOnEdge
      real (kind=RKIND), dimension(:,:), intent(in) :: adv_coefs, adv_coefs_3rd, coeffs_edge_midpoint
      real (kind=RKIND), dimension(nEdges+1), intent(in) :: invDvEdge, coeffs_edge_midpoint_own
      real (kind=RKIND), dimension(nVertLevels), intent(in) :: fzm, fzp
      real (kind=RKIND), dimension(nVertLevels,nEdges+1), intent(in) :: ru, ru_save
      real (kind=RKIND), dimension(nVertLevels,nCells+1), intent(in) :: theta_m, theta_m_save
      real (kind=RKIND), dimension(nVertLevels+1,nCells+1), intent(in) :: w
      real (kind=RKIND), dimension(nVertLevels,nEdges+1), intent(inout) :: flux_theta_edge, ru_midpoint
      real (kind=RKIND), dimension(nVertLevels+1,nEdges+1), intent(inout) :: flux_w_edge

      real (kind=RKIND), dimension(nVertLevels) :: ft, fw, ru_edge_w, sign_w
      real (kind=RKIND) :: scalar_weight
      integer :: iEdge, j, k, iAdvCell, cell1, cell2, eoe

      !$acc parallel default(present)
      !$acc loop gang worker private(ft, fw, ru_edge_w, sign_w)
      do iEdge = edgeStart, edgeEnd

         !$acc loop vector
         do k = 1, nVertLevels
            ft(k) = 0.0_RKIND
            fw(k) = 0.0_RKIND
         end do
         !$acc loop vector
         do k = 2, nVertLevels
            ru_edge_w(k) = fzm(k)*ru(k,iEdge) + fzp(k)*ru(k-1,iEdge)
            sign_w(k) = sign(1.0_RKIND,ru_edge_w(k))
         end do

         !$acc loop seq
         do j = 1, nAdvCellsForEdge(iEdge)
            iAdvCell = advCellsForEdge(j,iEdge)
            !$acc loop vector
            do k = 1, nVertLevels
               scalar_weight = adv_coefs(j,iEdge) + sign(1.0_RKIND,ru(k,iEdge)) * adv_coefs_3rd(j,iEdge)
               ft(k) = ft(k) + scalar_weight * theta_m(k,iAdvCell)
            end do
            !$acc loop vector
            do k = 2, nVertLevels
               scalar_weight = adv_coefs(j,iEdge) + sign_w(k) * adv_coefs_3rd(j,iEdge)
               fw(k) = fw(k) + scalar_weight * w(k,iAdvCell)
            end do
         end do

!DIR$ IVDEP
         !$acc loop vector
         do k = 1, nVertLevels
            flux_theta_edge(k,iEdge) = ru(k,iEdge) * ft(k) * invDvEdge(iEdge)
         end do
         if (rk_step > 1) then
            cell1 = cellsOnEdge(1,iEdge)
            cell2 = cellsOnEdge(2,iEdge)
!DIR$ IVDEP
            !$acc loop vector
            do k = 1, nVertLevels
               flux_theta_edge(k,iEdge) = flux_theta_edge(k,iEdge) &
                                          + (ru_save(k,iEdge)-ru(k,iEdge)) * 0.5_RKIND*(theta_m_save(k,cell2)+theta_m_save(k,cell1))
            end do
         end if

         flux_w_edge(1,iEdge) = 0.0_RKIND
         flux_w_edge(nVertLevels+1,iEdge) = 0.0_RKIND
!DIR$ IVDEP
         !$acc loop vector
         do k = 2, nVertLevels
            flux_w_edge(k,iEdge) = ru_edge_w(k) * fw(k) * invDvEdge(iEdge)
         end do

         !$acc loop vector
         do k = 1, nVertLevels
            ru_midpoint(k,iEdge) = coeffs_edge_midpoint_own(iEdge) * ru(k,iEdge)
         end do
         !$acc loop seq
         do j = 1, nEdgesOnEdge(iEdge)
            eoe = edgesOnEdge(j,iEdge)
!DIR$ IVDEP
            !$acc loop vector
            do k = 1, nVertLevels
               ru_midpoint(k,iEdge) = ru_midpoint(k,iEdge) + coeffs_edge_midpoint(j,iEdge) * ru(k,eoe)
            end do
         end do

      end do
      !$acc end parallel

   end subroutine atm_compute_edge_fluxes_work


   !-----------------------------------------------------------------------
   !  routine atm_compute_midpoint_fluxes
   !
   !> \brief Fluxes of theta_m and w at the Voronoi edge midpoints
   !> \author Pedro Peixoto
   !> \date   17 November 2026
   !> \details
   !>  After the exchange of 'dynamics:edge_fluxes', the horizontal fluxes per unit
   !>  length of theta_m and w at the Voronoi edge midpoint from those at x_t, on
   !>  the edges of the owned cells in edgeStart:edgeEnd, for the advection of
   !>  theta_m and w in atm_compute_dyn_tend.
   !
   !-----------------------------------------------------------------------
   subroutine atm_compute_midpoint_fluxes(diag, mesh, edgeStart, edgeEnd)

      implicit none

      type (mpas_pool_type), intent(inout) :: diag
      type (mpas_pool_type), intent(in) :: mesh
      integer, intent(in) :: edgeStart, edgeEnd

      integer, pointer :: nEdges, nCellsSolve
      integer, dimension(:), pointer :: nEdgesOnEdge
      integer, dimension(:,:), pointer :: cellsOnEdge, edgesOnEdge
      real (kind=RKIND), dimension(:), pointer :: coeffs_edge_midpoint_own
      real (kind=RKIND), dimension(:,:), pointer :: coeffs_edge_midpoint, flux_theta_edge, flux_w_edge, &
                                                    flux_theta_midpoint, flux_w_midpoint

      call mpas_pool_get_dimension(mesh, 'nEdges', nEdges)
      call mpas_pool_get_dimension(mesh, 'nCellsSolve', nCellsSolve)
      call mpas_pool_get_array(mesh, 'cellsOnEdge', cellsOnEdge)
      call mpas_pool_get_array(mesh, 'nEdgesOnEdge', nEdgesOnEdge)
      call mpas_pool_get_array(mesh, 'edgesOnEdge', edgesOnEdge)
      call mpas_pool_get_array(mesh, 'coeffs_edge_midpoint', coeffs_edge_midpoint)
      call mpas_pool_get_array(mesh, 'coeffs_edge_midpoint_own', coeffs_edge_midpoint_own)
      call mpas_pool_get_array(diag, 'flux_theta_edge', flux_theta_edge)
      call mpas_pool_get_array(diag, 'flux_w_edge', flux_w_edge)
      call mpas_pool_get_array(diag, 'flux_theta_midpoint', flux_theta_midpoint)
      call mpas_pool_get_array(diag, 'flux_w_midpoint', flux_w_midpoint)

      call atm_compute_midpoint_fluxes_work(nEdges, nCellsSolve, cellsOnEdge, nEdgesOnEdge, edgesOnEdge, &
                                            coeffs_edge_midpoint, coeffs_edge_midpoint_own, flux_theta_edge, flux_w_edge, &
                                            flux_theta_midpoint, flux_w_midpoint, edgeStart, edgeEnd)

   end subroutine atm_compute_midpoint_fluxes


   subroutine atm_compute_midpoint_fluxes_work(nEdges, nCellsSolve, cellsOnEdge, nEdgesOnEdge, edgesOnEdge, &
                                               coeffs_edge_midpoint, coeffs_edge_midpoint_own, flux_theta_edge, flux_w_edge, &
                                               flux_theta_midpoint, flux_w_midpoint, edgeStart, edgeEnd)

      implicit none

      integer, intent(in) :: nEdges, nCellsSolve, edgeStart, edgeEnd
      integer, dimension(2,nEdges+1), intent(in) :: cellsOnEdge
      integer, dimension(nEdges+1), intent(in) :: nEdgesOnEdge
      integer, dimension(:,:), intent(in) :: edgesOnEdge
      real (kind=RKIND), dimension(:,:), intent(in) :: coeffs_edge_midpoint
      real (kind=RKIND), dimension(nEdges+1), intent(in) :: coeffs_edge_midpoint_own
      real (kind=RKIND), dimension(nVertLevels,nEdges+1), intent(in) :: flux_theta_edge
      real (kind=RKIND), dimension(nVertLevels+1,nEdges+1), intent(in) :: flux_w_edge
      real (kind=RKIND), dimension(nVertLevels,nEdges+1), intent(inout) :: flux_theta_midpoint
      real (kind=RKIND), dimension(nVertLevels+1,nEdges+1), intent(inout) :: flux_w_midpoint

      integer :: iEdge, j, k, eoe

      !$acc parallel default(present)
      !$acc loop gang worker
      do iEdge = edgeStart, edgeEnd
         if (cellsOnEdge(1,iEdge) <= nCellsSolve .or. cellsOnEdge(2,iEdge) <= nCellsSolve) then
            !$acc loop vector
            do k = 1, nVertLevels
               flux_theta_midpoint(k,iEdge) = coeffs_edge_midpoint_own(iEdge) * flux_theta_edge(k,iEdge)
            end do
            !$acc loop vector
            do k = 2, nVertLevels
               flux_w_midpoint(k,iEdge) = coeffs_edge_midpoint_own(iEdge) * flux_w_edge(k,iEdge)
            end do
            !$acc loop seq
            do j = 1, nEdgesOnEdge(iEdge)
               eoe = edgesOnEdge(j,iEdge)
!DIR$ IVDEP
               !$acc loop vector
               do k = 1, nVertLevels
                  flux_theta_midpoint(k,iEdge) = flux_theta_midpoint(k,iEdge) &
                                                 + coeffs_edge_midpoint(j,iEdge) * flux_theta_edge(k,eoe)
               end do
!DIR$ IVDEP
               !$acc loop vector
               do k = 2, nVertLevels
                  flux_w_midpoint(k,iEdge) = flux_w_midpoint(k,iEdge) + coeffs_edge_midpoint(j,iEdge) * flux_w_edge(k,eoe)
               end do
            end do
         end if
      end do
      !$acc end parallel

   end subroutine atm_compute_midpoint_fluxes_work


   !-----------------------------------------------------------------------
   !  routine atm_edge_midpoint_ruavg
   !
   !> \brief Midpoint mass flux in the time-averaged mass flux of the scalar transport
   !> \author Pedro Peixoto
   !> \date   17 November 2026
   !> \details
   !>  With config_edge_midpoint_flux the mass of a cell changes in each large step
   !>  by the divergence of the midpoint flux of ru_save plus that of the acoustic
   !>  increments at x_t, so ruAvg gets the same correction, (midpoint flux of
   !>  ru_save) - ru_save, on the edges of the owned cells in edgeStart:edgeEnd,
   !>  where the acoustic step accumulates ruAvg.
   !
   !-----------------------------------------------------------------------
   subroutine atm_edge_midpoint_ruavg(diag, mesh, edgeStart, edgeEnd)

      implicit none

      type (mpas_pool_type), intent(inout) :: diag
      type (mpas_pool_type), intent(in) :: mesh
      integer, intent(in) :: edgeStart, edgeEnd

      integer, pointer :: nEdges, nCellsSolve
      integer, dimension(:), pointer :: nEdgesOnEdge
      integer, dimension(:,:), pointer :: cellsOnEdge, edgesOnEdge
      real (kind=RKIND), dimension(:), pointer :: coeffs_edge_midpoint_own
      real (kind=RKIND), dimension(:,:), pointer :: coeffs_edge_midpoint, ruAvg, ru_save

      call mpas_pool_get_dimension(mesh, 'nEdges', nEdges)
      call mpas_pool_get_dimension(mesh, 'nCellsSolve', nCellsSolve)
      call mpas_pool_get_array(mesh, 'cellsOnEdge', cellsOnEdge)
      call mpas_pool_get_array(mesh, 'nEdgesOnEdge', nEdgesOnEdge)
      call mpas_pool_get_array(mesh, 'edgesOnEdge', edgesOnEdge)
      call mpas_pool_get_array(mesh, 'coeffs_edge_midpoint', coeffs_edge_midpoint)
      call mpas_pool_get_array(mesh, 'coeffs_edge_midpoint_own', coeffs_edge_midpoint_own)
      call mpas_pool_get_array(diag, 'ruAvg', ruAvg)
      call mpas_pool_get_array(diag, 'ru_save', ru_save)

      call atm_edge_midpoint_ruavg_work(nEdges, nCellsSolve, cellsOnEdge, nEdgesOnEdge, edgesOnEdge, coeffs_edge_midpoint, &
                                        coeffs_edge_midpoint_own, ruAvg, ru_save, edgeStart, edgeEnd)

   end subroutine atm_edge_midpoint_ruavg


   subroutine atm_edge_midpoint_ruavg_work(nEdges, nCellsSolve, cellsOnEdge, nEdgesOnEdge, edgesOnEdge, coeffs_edge_midpoint, &
                                           coeffs_edge_midpoint_own, ruAvg, ru_save, edgeStart, edgeEnd)

      implicit none

      integer, intent(in) :: nEdges, nCellsSolve, edgeStart, edgeEnd
      integer, dimension(2,nEdges+1), intent(in) :: cellsOnEdge
      integer, dimension(nEdges+1), intent(in) :: nEdgesOnEdge
      integer, dimension(:,:), intent(in) :: edgesOnEdge
      real (kind=RKIND), dimension(:,:), intent(in) :: coeffs_edge_midpoint
      real (kind=RKIND), dimension(nEdges+1), intent(in) :: coeffs_edge_midpoint_own
      real (kind=RKIND), dimension(nVertLevels,nEdges+1), intent(inout) :: ruAvg
      real (kind=RKIND), dimension(nVertLevels,nEdges+1), intent(in) :: ru_save

      real (kind=RKIND), dimension(nVertLevels) :: fmid
      integer :: iEdge, j, k, eoe

      !$acc parallel default(present)
      !$acc loop gang worker private(fmid)
      do iEdge = edgeStart, edgeEnd
         if (cellsOnEdge(1,iEdge) <= nCellsSolve .or. cellsOnEdge(2,iEdge) <= nCellsSolve) then
            !$acc loop vector
            do k = 1, nVertLevels
               fmid(k) = coeffs_edge_midpoint_own(iEdge) * ru_save(k,iEdge)
            end do
            !$acc loop seq
            do j = 1, nEdgesOnEdge(iEdge)
               eoe = edgesOnEdge(j,iEdge)
!DIR$ IVDEP
               !$acc loop vector
               do k = 1, nVertLevels
                  fmid(k) = fmid(k) + coeffs_edge_midpoint(j,iEdge) * ru_save(k,eoe)
               end do
            end do
!DIR$ IVDEP
            !$acc loop vector
            do k = 1, nVertLevels
               ruAvg(k,iEdge) = ruAvg(k,iEdge) + fmid(k) - ru_save(k,iEdge)
            end do
         end if
      end do
      !$acc end parallel

   end subroutine atm_edge_midpoint_ruavg_work


   !-----------------------------------------------------------------------
   !  routine perot_cell_weights
   !
   !> \brief Perot reconstruction of the velocity at a cell
   !> \author Pedro Peixoto
   !> \date   17 November 2026
   !> \details
   !>  v = (1/A) sum_i s_i l_i u_i (m_i - b), with b the generator, m_i and l_i the
   !>  midpoint and length of side i of the cell polygon projected onto the plane
   !>  tangent at b, A the area of that polygon and s_i the sign that makes u_i the
   !>  outward normal velocity. Slot i is the edge edgesOnCell(i), whose side joins
   !>  its verticesOnEdge.
   !
   !-----------------------------------------------------------------------
   subroutine perot_cell_weights(b, n, edges, vertices, signs, verticesOnEdge, xv, w)

      implicit none

      real (kind=R8KIND), dimension(3), intent(in) :: b
      integer, intent(in) :: n
      integer, dimension(:), intent(in) :: edges, vertices
      real (kind=RKIND), dimension(:), intent(in) :: signs
      integer, dimension(:,:), intent(in) :: verticesOnEdge
      real (kind=R8KIND), dimension(:,:), intent(in) :: xv
      real (kind=R8KIND), dimension(:,:), intent(out) :: w

      real (kind=R8KIND), dimension(3,n) :: p
      real (kind=R8KIND), dimension(3) :: p1, p2
      real (kind=R8KIND) :: area
      integer :: i

      do i = 1, n
         p(:,i) = project(xv(:,vertices(i)), b)
      end do
      area = fan_area(n, p)

      do i = 1, n
         p1 = project(xv(:,verticesOnEdge(1,edges(i))), b)
         p2 = project(xv(:,verticesOnEdge(2,edges(i))), b)
         w(:,i) = (real(signs(i), R8KIND) * norm2(p2 - p1) / area) * (0.5_R8KIND * (p1 + p2) - b)
      end do

   end subroutine perot_cell_weights


   !-----------------------------------------------------------------------
   !  routine perot_vertex_weights
   !
   !> \brief Perot reconstruction of the velocity at a vertex
   !> \author Pedro Peixoto
   !> \date   17 November 2026
   !> \details
   !>  The Perot reconstruction applied to k x v on the triangle of the generators
   !>  around the vertex b, projected onto the plane tangent at b: the side of edge j
   !>  joins its cellsOnEdge, and k x v has the outward normal component sigma_j u_j,
   !>  with sigma_j = 1 where k x n_j points out of the triangle. Then
   !>  v = -(1/A) sum_j sigma_j l_j u_j k x (m_j - b).
   !
   !-----------------------------------------------------------------------
   subroutine perot_vertex_weights(b, n, edges, cells, cellsOnEdge, xc, ne, w)

      implicit none

      real (kind=R8KIND), dimension(3), intent(in) :: b
      integer, intent(in) :: n
      integer, dimension(:), intent(in) :: edges, cells
      integer, dimension(:,:), intent(in) :: cellsOnEdge
      real (kind=R8KIND), dimension(:,:), intent(in) :: xc, ne
      real (kind=R8KIND), dimension(:,:), intent(out) :: w

      real (kind=R8KIND), dimension(3,n) :: q
      real (kind=R8KIND), dimension(3) :: q1, q2, centroid, m
      real (kind=R8KIND) :: area, sigma
      integer :: j

      do j = 1, n
         q(:,j) = project(xc(:,cells(j)), b)
      end do
      area = fan_area(n, q)
      centroid = sum(q, dim=2) / real(n, R8KIND)

      do j = 1, n
         q1 = project(xc(:,cellsOnEdge(1,edges(j))), b)
         q2 = project(xc(:,cellsOnEdge(2,edges(j))), b)
         m = 0.5_R8KIND * (q1 + q2)
         sigma = sign(1.0_R8KIND, dot_product(cross(b, ne(:,edges(j))), m - centroid))
         w(:,j) = (-sigma * norm2(q2 - q1) / area) * cross(b, m - b)
      end do

   end subroutine perot_vertex_weights


   !-----------------------------------------------------------------------
   !  routine perot_tangential_weights
   !
   !> \brief Tangential velocity of an edge from the Perot velocities of its cells
   !> \author Pedro Peixoto
   !> \date   17 November 2026
   !> \details
   !>  v = (1/2) sum over the two cells c of v_c . t_c, with v_c the Perot velocity
   !>  of cell c and t_c the edge projected onto the plane tangent at c, oriented as
   !>  k x n. Weights w(1:n) go with eoe(1:n), the edgesOnEdge of the edge, and
   !>  w(n+1) with the edge itself.
   !
   !-----------------------------------------------------------------------
   subroutine perot_tangential_weights(iEdge, n, eoe, cells, vertices, xc, xv, ne, nEdgesOnCell, edgesOnCell, wperot, w)

      implicit none

      integer, intent(in) :: iEdge, n
      integer, dimension(:), intent(in) :: eoe, cells, vertices, nEdgesOnCell
      integer, dimension(:,:), intent(in) :: edgesOnCell
      real (kind=R8KIND), dimension(:,:), intent(in) :: xc, xv
      real (kind=R8KIND), dimension(3), intent(in) :: ne
      real (kind=R8KIND), dimension(:,:,:), intent(in) :: wperot
      real (kind=R8KIND), dimension(:), intent(out) :: w

      real (kind=R8KIND), dimension(3) :: b, t
      integer :: side, c, i, j

      w = 0.0_R8KIND
      do side = 1, 2
         c = cells(side)
         b = xc(:,c)
         t = unit(project(xv(:,vertices(2)), b) - project(xv(:,vertices(1)), b))
         if (dot_product(t, cross(b, ne)) < 0.0_R8KIND) t = -t
         do i = 1, nEdgesOnCell(c)
            if (edgesOnCell(i,c) == iEdge) then
               w(n+1) = w(n+1) + 0.5_R8KIND * dot_product(wperot(:,i,c), t)
               cycle
            end if
            j = findloc(eoe(1:n), edgesOnCell(i,c), dim=1)
            if (j == 0) then
               call mpas_log_write('edgesOnEdge of edge $i misses edge $i of its cells', &
                                   intArgs=(/iEdge, edgesOnCell(i,c)/), messageType=MPAS_LOG_CRIT)
            end if
            w(j) = w(j) + 0.5_R8KIND * dot_product(wperot(:,i,c), t)
         end do
      end do

   end subroutine perot_tangential_weights


   ! stops if a position x(:,i) divided by sphere_radius is not on the unit sphere, as the projections assume
   subroutine check_unit_norm(fields, x, sphere_radius)

      implicit none

      character (len=*), intent(in) :: fields
      real (kind=R8KIND), dimension(:,:), intent(in) :: x
      real (kind=RKIND), intent(in) :: sphere_radius

      real (kind=R8KIND) :: d
      integer :: i

      do i = 1, size(x,2)
         d = norm2(x(:,i)) - 1.0_R8KIND
         if (abs(d) > unit_norm_tolerance) then
            call mpas_log_write(fields//' of index $i not on the sphere of the mesh attribute sphere_radius = $r:'// &
                                ' |x| / sphere_radius - 1 = $r', intArgs=(/i/), realArgs=(/sphere_radius, real(d, RKIND)/), &
                                messageType=MPAS_LOG_CRIT)
         end if
      end do

   end subroutine check_unit_norm


   ! whether the stencil of the midpoint flux of an edge (the edge and its edgesOnEdge) is in the block
   logical function midpoint_stencil_ok(iEdge, n, eoe, vertices, nEdges, nVertices, edge_ok)

      implicit none

      integer, intent(in) :: iEdge, n, nEdges, nVertices
      integer, dimension(:), intent(in) :: eoe, vertices
      logical, dimension(:), intent(in) :: edge_ok

      midpoint_stencil_ok = edge_ok(iEdge) .and. all(vertices(1:2) >= 1 .and. vertices(1:2) <= nVertices) .and. &
                            all(eoe(1:n) >= 1 .and. eoe(1:n) <= nEdges)
      if (midpoint_stencil_ok) midpoint_stencil_ok = all(edge_ok(eoe(1:n)))

   end function midpoint_stencil_ok


   !-----------------------------------------------------------------------
   !  routine edge_midpoint_weights
   !
   !> \brief Normal flux at the Voronoi edge midpoint from the fluxes at x_t
   !> \author Pedro Peixoto
   !> \date   17 November 2026
   !> \details
   !>  Fit of a linear vector field to the normal components at the points x_t of
   !>  the edge and of its edgesOnEdge, in the plane tangent at x_t of the edge with
   !>  the basis (n, k x n) and offsets in units of the arc between its cells. The
   !>  flux at the projected midpoint x_m of the Voronoi edge is that at x_t plus
   !>  n . (grad v) (x_m - x_t) of the fit: weight wown for the edge itself and
   !>  w(1:n) for eoe(1:n), its edgesOnEdge.
   !
   !-----------------------------------------------------------------------
   subroutine edge_midpoint_weights(iEdge, n, eoe, cells, vertices, xc, xv, xt, ne, w, wown)

      implicit none

      integer, intent(in) :: iEdge, n
      integer, dimension(:), intent(in) :: eoe, cells, vertices
      real (kind=R8KIND), dimension(:,:), intent(in) :: xc, xv, xt, ne
      real (kind=R8KIND), dimension(:), intent(out) :: w
      real (kind=R8KIND), intent(out) :: wown

      real (kind=R8KIND), dimension(nfit,n+1) :: P
      real (kind=R8KIND), dimension(3) :: b, e1, e2, dx
      real (kind=R8KIND), dimension(n+1) :: g
      real (kind=R8KIND) :: L
      integer, dimension(n+1) :: stencil

      stencil(1) = iEdge
      stencil(2:n+1) = eoe(1:n)
      b = xt(:,iEdge)
      e1 = ne(:,iEdge)
      e2 = unit(cross(b, e1))
      L = atan2(norm2(cross(xc(:,cells(1)), xc(:,cells(2)))), dot_product(xc(:,cells(1)), xc(:,cells(2))))

      call lsq2_fit(b, n+1, xt(:,stencil), ne(:,stencil), e1, e2, P, scale=L)

      dx = project(unit(xv(:,vertices(1)) + xv(:,vertices(2))), b) - b
      g = (P(fit_dadx1,:) * dot_product(dx, e1) + P(fit_dadx2,:) * dot_product(dx, e2)) / L

      wown = 1.0_R8KIND + g(1)
      w = 0.0_R8KIND
      w(1:n) = g(2:n+1)

   end subroutine edge_midpoint_weights


   !-----------------------------------------------------------------------
   !  routine lsq2_vector_weights
   !
   !> \brief Least-squares reconstruction of the velocity at a cell or vertex
   !> \author Pedro Peixoto
   !> \date   17 November 2026
   !> \details
   !>  Fit of a linear vector field to the normal velocities of the edges of the
   !>  cell or vertex b, at the edge points x_t, in the plane tangent at b with the
   !>  local east and north basis. The weights are those of the value at b.
   !
   !-----------------------------------------------------------------------
   subroutine lsq2_vector_weights(b, n, edges, xt, ne, w)

      implicit none

      real (kind=R8KIND), dimension(3), intent(in) :: b
      integer, intent(in) :: n
      integer, dimension(:), intent(in) :: edges
      real (kind=R8KIND), dimension(:,:), intent(in) :: xt, ne
      real (kind=R8KIND), dimension(:,:), intent(out) :: w

      real (kind=R8KIND), dimension(nfit,n) :: P
      real (kind=R8KIND), dimension(3) :: east, north
      real (kind=R8KIND) :: lon
      integer :: i

      lon = atan2(b(2), b(1))
      east = (/ -sin(lon), cos(lon), 0.0_R8KIND /)
      north = cross(b, east)

      call lsq2_fit(b, n, xt(:,edges(1:n)), ne(:,edges(1:n)), east, north, P)

      do i = 1, n
         w(:,i) = P(fit_a,i) * east + P(fit_b,i) * north
      end do

   end subroutine lsq2_vector_weights


   !-----------------------------------------------------------------------
   !  routine lsq2_fit
   !
   !> \brief Least-squares fit of a linear vector field to normal components
   !> \author Pedro Peixoto
   !> \date   17 November 2026
   !> \details
   !>  Rows of P (nfit x n) give the unknowns fit_* of the field from the normal
   !>  components at the points pos(:,1:n) with normals nrm(:,1:n), all projected
   !>  onto the plane tangent at b. Offsets are in units of scale if present, else
   !>  of their mean length. Poorly conditioned fits get their gradient terms
   !>  regularized (lsq_max_condition).
   !
   !-----------------------------------------------------------------------
   subroutine lsq2_fit(b, n, pos, nrm, e1, e2, P, scale)

      implicit none

      real (kind=R8KIND), dimension(3), intent(in) :: b, e1, e2
      integer, intent(in) :: n
      real (kind=R8KIND), dimension(3,n), intent(in) :: pos, nrm
      real (kind=R8KIND), dimension(nfit,n), intent(out) :: P
      real (kind=R8KIND), intent(in), optional :: scale

      real (kind=R8KIND), dimension(n,nfit) :: M
      real (kind=R8KIND), dimension(nfit,nfit) :: A
      real (kind=R8KIND), dimension(nfit) :: lambda
      real (kind=R8KIND), dimension(3,n) :: pp
      real (kind=R8KIND), dimension(3) :: nn, d
      real (kind=R8KIND) :: L, nx, ny, dx, dy, lmax
      integer :: i, j

      do i = 1, n
         pp(:,i) = project(pos(:,i), b)
      end do
      if (present(scale)) then
         L = scale
      else
         L = 0.0_R8KIND
         do i = 1, n
            L = L + norm2(pp(:,i) - b)
         end do
         L = L / real(n, R8KIND)
      end if

      do i = 1, n
         nn = nrm(:,i) - dot_product(nrm(:,i), b) * b
         nn = nn / norm2(nn)
         nx = dot_product(nn, e1)
         ny = dot_product(nn, e2)
         d = (pp(:,i) - b) / L
         dx = dot_product(d, e1)
         dy = dot_product(d, e2)
         M(i,fit_a) = nx
         M(i,fit_b) = ny
         M(i,fit_dadx1) = nx * dx
         M(i,fit_dbdx1) = ny * dx
         M(i,fit_dadx2) = nx * dy
         M(i,fit_dbdx2) = ny * dy
      end do

      A = matmul(transpose(M), M)
      call symmetric_eigenvalues(A, lambda)
      lmax = maxval(abs(lambda))
      if (lmax > lsq_max_condition * minval(abs(lambda))) then
         do j = fit_dadx1, nfit
            A(j,j) = A(j,j) + lmax / lsq_max_condition
         end do
      end if

      P = transpose(M)
      call cholesky_solve(A, P)

   end subroutine lsq2_fit


   !-----------------------------------------------------------------------
   !  routine symmetric_eigenvalues
   !
   !> \brief Eigenvalues of a small symmetric matrix (cyclic Jacobi)
   !> \author Pedro Peixoto
   !> \date   17 November 2026
   !
   !-----------------------------------------------------------------------
   subroutine symmetric_eigenvalues(A, lambda)

      implicit none

      real (kind=R8KIND), dimension(:,:), intent(in) :: A
      real (kind=R8KIND), dimension(:), intent(out) :: lambda

      real (kind=R8KIND), dimension(size(A,1),size(A,1)) :: B
      real (kind=R8KIND) :: off, tol, theta, t, c, s, bp, bq
      integer :: n, p, q, k, sweep

      n = size(A,1)
      B = A
      tol = (epsilon(1.0_R8KIND) * norm2(A))**2
      do sweep = 1, max_jacobi_sweeps
         off = 0.0_R8KIND
         do q = 2, n
            off = off + sum(B(1:q-1,q)**2)
         end do
         if (2.0_R8KIND * off <= tol) exit
         do p = 1, n-1
            do q = p+1, n
               if (B(p,q) == 0.0_R8KIND) cycle
               theta = (B(q,q) - B(p,p)) / (2.0_R8KIND * B(p,q))
               t = sign(1.0_R8KIND, theta) / (abs(theta) + hypot(1.0_R8KIND, theta))
               c = 1.0_R8KIND / hypot(1.0_R8KIND, t)
               s = t * c
               do k = 1, n
                  bp = B(k,p)
                  bq = B(k,q)
                  B(k,p) = c * bp - s * bq
                  B(k,q) = s * bp + c * bq
               end do
               do k = 1, n
                  bp = B(p,k)
                  bq = B(q,k)
                  B(p,k) = c * bp - s * bq
                  B(q,k) = s * bp + c * bq
               end do
            end do
         end do
      end do

      do k = 1, n
         lambda(k) = B(k,k)
      end do

   end subroutine symmetric_eigenvalues


   !-----------------------------------------------------------------------
   !  routine cholesky_solve
   !
   !> \brief Solves A Y = X in place of X, for a symmetric positive definite A
   !> \author Pedro Peixoto
   !> \date   17 November 2026
   !
   !-----------------------------------------------------------------------
   subroutine cholesky_solve(A, X)

      implicit none

      real (kind=R8KIND), dimension(:,:), intent(in) :: A
      real (kind=R8KIND), dimension(:,:), intent(inout) :: X

      real (kind=R8KIND), dimension(size(A,1),size(A,1)) :: L
      real (kind=R8KIND) :: s
      integer :: n, i, j

      n = size(A,1)
      L = 0.0_R8KIND
      do j = 1, n
         s = A(j,j) - sum(L(j,1:j-1)**2)
         if (s <= 0.0_R8KIND) then
            call mpas_log_write('mpas_atm_consistent_operators: least-squares normal matrix not positive definite', &
                                messageType=MPAS_LOG_CRIT)
         end if
         L(j,j) = sqrt(s)
         do i = j+1, n
            L(i,j) = (A(i,j) - sum(L(i,1:j-1) * L(j,1:j-1))) / L(j,j)
         end do
      end do

      do i = 1, n
         X(i,:) = (X(i,:) - matmul(L(i,1:i-1), X(1:i-1,:))) / L(i,i)
      end do
      do i = n, 1, -1
         X(i,:) = (X(i,:) - matmul(L(i+1:n,i), X(i+1:n,:))) / L(i,i)
      end do

   end subroutine cholesky_solve


   !-----------------------------------------------------------------------
   !  Small vector helpers
   !-----------------------------------------------------------------------
   pure function cross(a, b)

      implicit none

      real (kind=R8KIND), dimension(3), intent(in) :: a, b
      real (kind=R8KIND), dimension(3) :: cross

      cross = (/ a(2)*b(3) - a(3)*b(2), a(3)*b(1) - a(1)*b(3), a(1)*b(2) - a(2)*b(1) /)

   end function cross


   pure function unit(a)

      implicit none

      real (kind=R8KIND), dimension(3), intent(in) :: a
      real (kind=R8KIND), dimension(3) :: unit

      unit = a / norm2(a)

   end function unit


   ! gnomonic projection of the point p of the unit sphere onto the plane tangent at b
   pure function project(p, b)

      implicit none

      real (kind=R8KIND), dimension(3), intent(in) :: p, b
      real (kind=R8KIND), dimension(3) :: project

      project = p / dot_product(p, b)

   end function project


   ! area of the polygon p(:,1:n), as triangles fanning out from the mean of its corners
   pure function fan_area(n, p)

      implicit none

      integer, intent(in) :: n
      real (kind=R8KIND), dimension(3,n), intent(in) :: p
      real (kind=R8KIND) :: fan_area

      real (kind=R8KIND), dimension(3) :: center
      integer :: i

      center = sum(p, dim=2) / real(n, R8KIND)
      fan_area = 0.0_R8KIND
      do i = 1, n
         fan_area = fan_area + 0.5_R8KIND * norm2(cross(p(:,i) - center, p(:,mod(i,n)+1) - p(:,i)))
      end do

   end function fan_area

end module mpas_atm_consistent_operators
