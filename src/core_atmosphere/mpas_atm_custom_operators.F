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

      logical, pointer :: config_use_custom_weightsOnEdge
      logical, pointer :: config_use_custom_coeffs_reconstruct

      call mpas_pool_get_config(block % configs, 'config_use_custom_weightsOnEdge', config_use_custom_weightsOnEdge)

      if (config_use_custom_weightsOnEdge) then

         call mpas_pool_get_array(mesh, 'weightsOnEdge', weightsOnEdge)
         call mpas_pool_get_array(mesh, 'coeffs_edge_tanVel_reconstruct', new_weightsOnEdge)

         weightsOnEdge(:,:) = new_weightsOnEdge(:,:)

      end if

      call mpas_pool_get_config(block % configs, 'config_use_custom_coeffs_reconstruct', config_use_custom_coeffs_reconstruct)

      if (config_use_custom_coeffs_reconstruct) then

         call mpas_pool_get_array(mesh, 'coeffs_reconstruct', coeffs_reconstruct)
         call mpas_pool_get_array(mesh, 'coeffs_cell_vel_reconstruct', new_coeffs_reconstruct)

         coeffs_reconstruct(:,:,:) = new_coeffs_reconstruct(:,:,:)

      end if

   end subroutine mpas_atm_init_custom_operators

end module mpas_atm_custom_operators
