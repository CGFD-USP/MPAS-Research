module mpas_atm_custom_operators

   use mpas_derived_types
   use mpas_pool_routines

   contains

   subroutine mpas_atm_init_custom_operators(block, mesh)

      implicit none

      type (block_type), intent(inout) :: block
      type (mpas_pool_type), intent(inout) :: mesh

      real (kind=RKIND), dimension(:,:), pointer :: weightsOnEdge, new_weightsOnEdge
      real (kind=RKIND), dimension(:,:,:), pointer :: coeffs_reconstruct, new_coeffs_reconstruct
      real (kind=RKIND), dimension(:,:), pointer :: kiteAreasOnVertex, new_kiteAreasOnVertex
      real (kind=RKIND), dimension(:), pointer :: areaCell, new_areaCell, areaTriangle, new_areaTriangle
      real (kind=RKIND), dimension(:), pointer :: invAreaCell, invAreaTriangle

      logical, pointer :: config_use_custom_weightsOnEdge
      logical, pointer :: config_use_custom_coeffs_reconstruct
      logical, pointer :: config_use_custom_areas

      integer, pointer :: trueMaxEdges2_ptr
      integer :: trueMaxEdges2

      call mpas_pool_get_config(block % configs, 'config_use_custom_weightsOnEdge', config_use_custom_weightsOnEdge)

      if (config_use_custom_weightsOnEdge) then

         call mpas_pool_get_array(mesh, 'weightsOnEdge', weightsOnEdge)
         call mpas_pool_get_array(mesh, 'coeffs_edge_tanVel_reconstruct', new_weightsOnEdge)
         call mpas_pool_get_dimension(mesh, 'trueMaxEdges2', trueMaxEdges2_ptr)

         trueMaxEdges2 = trueMaxEdges2_ptr

         weightsOnEdge(1:trueMaxEdges2,:) = new_weightsOnEdge(1:trueMaxEdges2,:)

      end if

      call mpas_pool_get_config(block % configs, 'config_use_custom_coeffs_reconstruct', config_use_custom_coeffs_reconstruct)

      if (config_use_custom_coeffs_reconstruct) then

         call mpas_pool_get_array(mesh, 'coeffs_reconstruct', coeffs_reconstruct)
         call mpas_pool_get_array(mesh, 'coeffs_cell_vel_reconstruct', new_coeffs_reconstruct)

         coeffs_reconstruct(:,:,:) = new_coeffs_reconstruct(:,:,:)

      end if

      call mpas_pool_get_config(block % configs, 'config_use_custom_areas', config_use_custom_areas)

      if (config_use_custom_areas) then

         call mpas_pool_get_array(mesh, 'areaCell', areaCell)
         call mpas_pool_get_array(mesh, 'invAreaCell', invAreaCell)
         call mpas_pool_get_array(mesh, 'custom_areaCell', new_areaCell)

         areaCell(:) = new_areaCell(:)
         invAreaCell(:) = 1.0_RKIND / new_areaCell(:)

         call mpas_pool_get_array(mesh, 'areaTriangle', areaTriangle)
         call mpas_pool_get_array(mesh, 'invAreaTriangle', invAreaTriangle)
         call mpas_pool_get_array(mesh, 'custom_areaTriangle', new_areaTriangle)

         areaTriangle(:) = new_areaTriangle(:)
         invAreaTriangle(:) = 1.0_RKIND / new_areaTriangle(:)

         call mpas_pool_get_array(mesh, 'kiteAreasOnVertex', kiteAreasOnVertex)
         call mpas_pool_get_array(mesh, 'custom_kiteAreasOnVertex', new_kiteAreasOnVertex)

         kiteAreasOnVertex(:,:) = new_kiteAreasOnVertex(:,:)

      end if

   end subroutine mpas_atm_init_custom_operators

end module mpas_atm_custom_operators
