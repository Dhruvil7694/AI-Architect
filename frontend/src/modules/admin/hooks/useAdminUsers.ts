import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/lib/queryKeys";
import {
  getUsers,
  getUser,
  createUser,
  updateUser,
  deactivateUser,
  type AdminUser,
  type CreateUserPayload,
  type UpdateUserPayload,
  type GetUsersParams,
} from "@/services/adminService";

export function useUsersQuery(params: GetUsersParams = {}) {
  return useQuery<AdminUser[]>({
    queryKey: queryKeys.admin.users.list(params),
    queryFn: () => getUsers(params),
  });
}

export function useUserQuery(id: string) {
  return useQuery<AdminUser>({
    queryKey: queryKeys.admin.users.detail(id),
    queryFn: () => getUser(id),
  });
}

export function useCreateUserMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateUserPayload) => createUser(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.admin.users.list(undefined),
      });
    },
  });
}

export function useUpdateUserMutation(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: UpdateUserPayload) => updateUser(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.admin.users.detail(id),
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.admin.users.list(undefined),
      });
    },
  });
}

export function useDeactivateUserMutation(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => deactivateUser(id),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.admin.users.list(undefined),
      });
    },
  });
}

