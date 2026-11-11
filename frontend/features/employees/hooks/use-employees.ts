"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { authQueryKeys } from "@/services/auth";
import { dashboardQueryKeys } from "@/services/dashboard";
import {
  createAccount,
  createDepartment,
  employeeQueryKeys,
  getEmployee,
  getHrProfile,
  listDepartmentsFull,
  listEmployees,
  replaceHrProfile,
  setAccountActive,
  setAccountRoles,
  updateAccount,
  updateDepartment,
  type AccountInput,
  type CreateAccountInput,
  type DepartmentInput,
  type EmployeeListParams,
  type HrProfileInput,
} from "@/services/employees";

export function useEmployeeList(params: EmployeeListParams, enabled = true) {
  return useQuery({
    queryKey: employeeQueryKeys.list(params),
    queryFn: ({ signal }) => listEmployees(params, signal),
    placeholderData: (previous) => previous,
    staleTime: 30_000,
    enabled,
  });
}

export function useEmployee(id: string) {
  return useQuery({
    queryKey: employeeQueryKeys.profile(id),
    queryFn: ({ signal }) => getEmployee(id, signal),
  });
}

/** Someone else's HR record is fetched only on request: every such read is audit-logged. */
export function useHrProfile(id: string, enabled: boolean) {
  return useQuery({
    queryKey: employeeQueryKeys.hr(id),
    queryFn: ({ signal }) => getHrProfile(id, signal),
    enabled,
    staleTime: Infinity,
    gcTime: 60_000,
  });
}

export function useDepartmentsFull() {
  return useQuery({
    queryKey: employeeQueryKeys.departments,
    queryFn: ({ signal }) => listDepartmentsFull(signal),
    staleTime: 60_000,
  });
}

function useInvalidatePeople() {
  const client = useQueryClient();
  return () =>
    Promise.all([
      client.invalidateQueries({ queryKey: employeeQueryKeys.all }),
      client.invalidateQueries({ queryKey: ["departments"] }),
      client.invalidateQueries({ queryKey: dashboardQueryKeys.summary }),
      // The signed-in user may have edited their own account.
      client.invalidateQueries({ queryKey: authQueryKeys.me }),
    ]);
}

export function useCreateAccount() {
  const invalidate = useInvalidatePeople();
  return useMutation({
    mutationFn: (input: CreateAccountInput) => createAccount(input),
    onSuccess: () => invalidate(),
  });
}

export function useUpdateAccount(id: string) {
  const invalidate = useInvalidatePeople();
  return useMutation({
    mutationFn: (input: Partial<AccountInput>) => updateAccount(id, input),
    onSuccess: () => invalidate(),
  });
}

export function useSetActive(id: string) {
  const invalidate = useInvalidatePeople();
  return useMutation({
    mutationFn: (active: boolean) => setAccountActive(id, active),
    onSuccess: () => invalidate(),
  });
}

export function useSetRoles(id: string) {
  const invalidate = useInvalidatePeople();
  return useMutation({
    mutationFn: (codes: string[]) => setAccountRoles(id, codes),
    onSuccess: () => invalidate(),
  });
}

export function useReplaceHrProfile(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: HrProfileInput) => replaceHrProfile(id, input),
    onSuccess: (data) => client.setQueryData(employeeQueryKeys.hr(id), data),
  });
}

export function useSaveDepartment(id: string | null) {
  const invalidate = useInvalidatePeople();
  return useMutation({
    mutationFn: (input: DepartmentInput) =>
      id ? updateDepartment(id, input) : createDepartment(input),
    onSuccess: () => invalidate(),
  });
}
