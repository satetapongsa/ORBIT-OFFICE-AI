"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { TaskPriority } from "@/services/tasks";
import { notificationQueryKeys } from "@/services/notifications";
import {
  addTicketComment,
  assignTicket,
  changeTicketStatus,
  createTicket,
  getTicket,
  getTicketHistory,
  listTicketAssignees,
  listTicketComments,
  listTickets,
  ticketQueryKeys,
  updateTicket,
  type TicketCategory,
  type TicketInput,
  type TicketListParams,
  type TicketStatus,
} from "@/services/tickets";

export function useTicketList(params: TicketListParams) {
  return useQuery({
    queryKey: ticketQueryKeys.list(params),
    queryFn: ({ signal }) => listTickets(params, signal),
    placeholderData: (previous) => previous,
    staleTime: 10_000,
  });
}

export function useTicket(id: string) {
  return useQuery({
    queryKey: ticketQueryKeys.detail(id),
    queryFn: ({ signal }) => getTicket(id, signal),
  });
}

export function useTicketComments(id: string) {
  return useQuery({
    queryKey: ticketQueryKeys.comments(id),
    queryFn: ({ signal }) => listTicketComments(id, signal),
  });
}

export function useTicketHistory(id: string) {
  return useQuery({
    queryKey: ticketQueryKeys.history(id),
    queryFn: ({ signal }) => getTicketHistory(id, signal),
  });
}

export function useTicketAssignees(enabled: boolean) {
  return useQuery({
    queryKey: ticketQueryKeys.assignees,
    queryFn: ({ signal }) => listTicketAssignees(signal),
    enabled,
    staleTime: 60_000,
  });
}

function useInvalidateTickets() {
  const client = useQueryClient();
  return () =>
    Promise.all([
      client.invalidateQueries({ queryKey: ticketQueryKeys.all }),
      client.invalidateQueries({ queryKey: notificationQueryKeys.all }),
    ]);
}

export function useCreateTicket() {
  const invalidate = useInvalidateTickets();
  return useMutation({
    mutationFn: (input: TicketInput) => createTicket(input),
    onSuccess: () => invalidate(),
  });
}

export function useChangeTicketStatus(id: string) {
  const invalidate = useInvalidateTickets();
  return useMutation({
    mutationFn: (status: TicketStatus) => changeTicketStatus(id, status),
    onSuccess: () => invalidate(),
  });
}

export function useAssignTicket(id: string) {
  const invalidate = useInvalidateTickets();
  return useMutation({
    mutationFn: (assigneeId: string | null) => assignTicket(id, assigneeId),
    onSuccess: () => invalidate(),
  });
}

export function useUpdateTicket(id: string) {
  const invalidate = useInvalidateTickets();
  return useMutation({
    mutationFn: (input: { category?: TicketCategory; priority?: TaskPriority }) =>
      updateTicket(id, input),
    onSuccess: () => invalidate(),
  });
}

export function useAddTicketComment(id: string) {
  const invalidate = useInvalidateTickets();
  return useMutation({
    mutationFn: ({ body, internal }: { body: string; internal: boolean }) =>
      addTicketComment(id, body, internal),
    onSuccess: () => invalidate(),
  });
}
