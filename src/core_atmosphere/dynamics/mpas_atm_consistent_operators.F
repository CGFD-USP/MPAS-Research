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
!>  and of the Voronoi vertices, for the kinetic energy option
!>  config_ke_reconstruction: the velocity vector at cells and vertices from the
!>  normal velocities of their edges, by the reconstruction of Perot ('perot') or
!>  by a least-squares fit of a linear vector field ('lsq2'). The cell weights
!>  replace the coefficients coeffs_reconstruct of mpas_vector_reconstruction, the
!>  vertex weights go to coeffs_reconstruct_vertex.
!>
!>  Positions are taken on the unit sphere and projected (gnomonic projection)
!>  onto the plane tangent at the cell or vertex. A weight is computed only where
!>  all its inputs are in the block; elsewhere the cell keeps the coefficients of
!>  mpas_init_reconstruct and the vertex gets zero weights.
!
!-----------------------------------------------------------------------
module mpas_atm_consistent_operators

   use mpas_kind_types, only : RKIND, R8KIND, StrKIND
   use mpas_derived_types, only : mpas_pool_type, MPAS_LOG_CRIT
   use mpas_pool_routines, only : mpas_pool_get_array, mpas_pool_get_dimension, mpas_pool_get_config
   use mpas_log, only : mpas_log_write
   use mpas_timer, only : mpas_timer_start, mpas_timer_stop

   implicit none

   private
   public :: atm_consistent_operators_init

   ! Unknowns of the least-squares fit of a linear vector field (a, b) + G x, with components a, b along the
   ! basis vectors e1, e2 and offsets x along them: a, b, da/dx1, db/dx1, da/dx2, db/dx2
   integer, parameter :: fit_a = 1, fit_b = 2, fit_dadx1 = 3, fit_dbdx1 = 4, fit_dadx2 = 5, fit_dbdx2 = 6
   integer, parameter :: nfit = 6

   ! A fit whose normal matrix has a larger condition number gets its gradient terms
   ! regularized by the norm of that matrix divided by this number
   real (kind=R8KIND), parameter :: lsq_max_condition = 5.0e6_R8KIND

   ! Largest number of sweeps of the Jacobi eigenvalue iteration (it converges in a few)
   integer, parameter :: max_jacobi_sweeps = 50


   contains


   !-----------------------------------------------------------------------
   !  routine atm_consistent_operators_init
   !
   !> \brief Computes the weights of the selected options
   !> \author Pedro Peixoto
   !> \date   17 November 2026
   !> \details
   !>  Called once per block at start-up, after mpas_init_reconstruct and before
   !>  the first diagnostics. Does nothing with the default options.
   !
   !-----------------------------------------------------------------------
   subroutine atm_consistent_operators_init(mesh, configs)

      implicit none

      type (mpas_pool_type), intent(inout) :: mesh
      type (mpas_pool_type), intent(in) :: configs

      character (len=StrKIND), pointer :: config_ke_reconstruction
      logical, pointer :: on_a_sphere
      real (kind=RKIND), pointer :: sphere_radius
      integer, pointer :: nCells, nEdges, nVertices, nCellsSolve, nVerticesSolve, vertexDegree
      integer, dimension(:), pointer :: nEdgesOnCell
      integer, dimension(:,:), pointer :: edgesOnCell, verticesOnCell, verticesOnEdge, cellsOnEdge, &
                                          edgesOnVertex, cellsOnVertex
      real (kind=RKIND), dimension(:), pointer :: xCell, yCell, zCell, xVertex, yVertex, zVertex
      real (kind=RKIND), dimension(:,:), pointer :: edgesOnCell_sign
      real (kind=RKIND), dimension(:,:,:), pointer :: coeffs_reconstruct, coeffs_reconstruct_vertex

      real (kind=R8KIND), dimension(:,:), allocatable :: xc, xv, xt, ne
      logical, dimension(:), allocatable :: cell_ok, vertex_ok, edge_ok
      real (kind=R8KIND), dimension(:,:), allocatable :: wc, wv
      real (kind=R8KIND) :: r
      integer :: iCell, iEdge, iVertex, n

      call mpas_pool_get_config(configs, 'config_ke_reconstruction', config_ke_reconstruction)
      if (trim(config_ke_reconstruction) == 'trsk') return

      call mpas_timer_start('atm_consistent_operators_init')

      call mpas_pool_get_config(mesh, 'on_a_sphere', on_a_sphere)
      if (.not. on_a_sphere) then
         call mpas_log_write('config_ke_reconstruction = '''//trim(config_ke_reconstruction)//''' needs a spherical mesh', &
                             messageType=MPAS_LOG_CRIT)
      end if
      call mpas_pool_get_config(mesh, 'sphere_radius', sphere_radius)

      call mpas_pool_get_dimension(mesh, 'nCells', nCells)
      call mpas_pool_get_dimension(mesh, 'nEdges', nEdges)
      call mpas_pool_get_dimension(mesh, 'nVertices', nVertices)
      call mpas_pool_get_dimension(mesh, 'nCellsSolve', nCellsSolve)
      call mpas_pool_get_dimension(mesh, 'nVerticesSolve', nVerticesSolve)
      call mpas_pool_get_dimension(mesh, 'vertexDegree', vertexDegree)

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
      call mpas_pool_get_array(mesh, 'edgesOnVertex', edgesOnVertex)
      call mpas_pool_get_array(mesh, 'cellsOnVertex', cellsOnVertex)
      call mpas_pool_get_array(mesh, 'edgesOnCell_sign', edgesOnCell_sign)
      call mpas_pool_get_array(mesh, 'coeffs_reconstruct', coeffs_reconstruct)
      call mpas_pool_get_array(mesh, 'coeffs_reconstruct_vertex', coeffs_reconstruct_vertex)

      ! positions on the unit sphere
      r = 1.0_R8KIND / real(sphere_radius, R8KIND)
      allocate(xc(3,nCells), xv(3,nVertices))
      do iCell = 1, nCells
         xc(:,iCell) = (/ real(xCell(iCell), R8KIND), real(yCell(iCell), R8KIND), real(zCell(iCell), R8KIND) /) * r
      end do
      do iVertex = 1, nVertices
         xv(:,iVertex) = (/ real(xVertex(iVertex), R8KIND), real(yVertex(iVertex), R8KIND), real(zVertex(iVertex), R8KIND) /) * r
      end do

      ! edges whose two cells are in the block: point x_t (midpoint of the arc between the cells) and unit normal
      allocate(xt(3,nEdges), ne(3,nEdges), edge_ok(nEdges))
      do iEdge = 1, nEdges
         edge_ok(iEdge) = all(cellsOnEdge(:,iEdge) >= 1 .and. cellsOnEdge(:,iEdge) <= nCells)
         if (edge_ok(iEdge)) then
            xt(:,iEdge) = unit(xc(:,cellsOnEdge(1,iEdge)) + xc(:,cellsOnEdge(2,iEdge)))
            ne(:,iEdge) = unit(xc(:,cellsOnEdge(2,iEdge)) - xc(:,cellsOnEdge(1,iEdge)))
         end if
      end do

      allocate(cell_ok(nCells), vertex_ok(nVertices))
      do iCell = 1, nCells
         n = nEdgesOnCell(iCell)
         cell_ok(iCell) = all(edgesOnCell(1:n,iCell) >= 1 .and. edgesOnCell(1:n,iCell) <= nEdges) .and. &
                          all(verticesOnCell(1:n,iCell) >= 1 .and. verticesOnCell(1:n,iCell) <= nVertices)
         if (cell_ok(iCell) .and. trim(config_ke_reconstruction) == 'lsq2') then
            cell_ok(iCell) = all(edge_ok(edgesOnCell(1:n,iCell)))
         end if
      end do
      do iVertex = 1, nVertices
         vertex_ok(iVertex) = all(edgesOnVertex(:,iVertex) >= 1 .and. edgesOnVertex(:,iVertex) <= nEdges) .and. &
                              all(cellsOnVertex(:,iVertex) >= 1 .and. cellsOnVertex(:,iVertex) <= nCells)
         if (vertex_ok(iVertex)) vertex_ok(iVertex) = all(edge_ok(edgesOnVertex(:,iVertex)))
      end do

      allocate(wc(3,size(coeffs_reconstruct,2)), wv(3,vertexDegree))
      do iCell = 1, nCells
         if (.not. cell_ok(iCell)) cycle
         n = nEdgesOnCell(iCell)
         if (trim(config_ke_reconstruction) == 'perot') then
            call perot_cell_weights(xc(:,iCell), n, edgesOnCell(:,iCell), verticesOnCell(:,iCell), &
                                    edgesOnCell_sign(:,iCell), verticesOnEdge, xv, wc)
         else
            call lsq2_vector_weights(xc(:,iCell), n, edgesOnCell(:,iCell), xt, ne, wc)
         end if
         coeffs_reconstruct(:,:,iCell) = 0.0_RKIND
         coeffs_reconstruct(:,1:n,iCell) = real(wc(:,1:n), RKIND)
      end do

      do iVertex = 1, nVertices
         coeffs_reconstruct_vertex(:,:,iVertex) = 0.0_RKIND
         if (.not. vertex_ok(iVertex)) cycle
         if (trim(config_ke_reconstruction) == 'perot') then
            call perot_vertex_weights(xv(:,iVertex), vertexDegree, edgesOnVertex(:,iVertex), cellsOnVertex(:,iVertex), &
                                      cellsOnEdge, xc, ne, wv)
         else
            call lsq2_vector_weights(xv(:,iVertex), vertexDegree, edgesOnVertex(:,iVertex), xt, ne, wv)
         end if
         coeffs_reconstruct_vertex(:,:,iVertex) = real(wv, RKIND)
      end do

      call mpas_log_write('Kinetic energy and cell velocity from the '//trim(config_ke_reconstruction)// &
                          ' reconstruction; owned cells and vertices without it: $i $i', &
                          intArgs=(/count(.not. cell_ok(1:nCellsSolve)), count(.not. vertex_ok(1:nVerticesSolve))/))

      deallocate(xc, xv, xt, ne, edge_ok, cell_ok, vertex_ok, wc, wv)

      call mpas_timer_stop('atm_consistent_operators_init')

   end subroutine atm_consistent_operators_init


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

      call lsq2_fit(b, n, xt(:,edges(1:n)), ne(:,edges(1:n)), east, north, 0.0_R8KIND, P)

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
   !>  onto the plane tangent at b. Offsets are in units of scale, or of their mean
   !>  length if scale is zero. Poorly conditioned fits get their gradient terms
   !>  regularized (lsq_max_condition).
   !
   !-----------------------------------------------------------------------
   subroutine lsq2_fit(b, n, pos, nrm, e1, e2, scale, P)

      implicit none

      real (kind=R8KIND), dimension(3), intent(in) :: b, e1, e2
      integer, intent(in) :: n
      real (kind=R8KIND), dimension(3,n), intent(in) :: pos, nrm
      real (kind=R8KIND), intent(in) :: scale
      real (kind=R8KIND), dimension(nfit,n), intent(out) :: P

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
      if (scale > 0.0_R8KIND) then
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
