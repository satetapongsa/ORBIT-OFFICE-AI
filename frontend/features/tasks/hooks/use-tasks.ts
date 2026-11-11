"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { dashboardQueryKeys } from "@/services/dashboard";
import { notificationQueryKeys } from "@/services/notifications";
import {
  addComment,
  changeTaskStatus,
  createTask,
  deleteAttachment,
  deleteComment,
  deleteTask,
  editComment,
  getTask,
  getTaskHistory,
  listAttachments,
  listComments,
  listTasks,
  replaceAssignees,
  searchAssignable,
  taskQueryKeys,
  updateTask,
  uploadAttachment,
  type TaskInput,
  type TaskListParams,
  type TaskStatus,
} from "@/services/tasks";

export function useTaskList(params: TaskListParams) {
  return useQuery({
    queryKey: taskQueryKeys.list(params),
    queryFn: ({ signal }) => listTasks(params, signal),
    placeholderData: (previous) => previous,
    staleTime: 10_000,
  });
}

export function useTask(id: string) {
  return useQuery({
    queryKey: taskQueryKeys.detail(id),
    queryFn: ({ signal }) => getTask(id, signal),
  });
}

export function useTaskComments(id: string) {
  return useQuery({
    queryKey: taskQueryKeys.comments(id),
    queryFn: ({ signal }) => listComments(id, signal),
  });
}

export function useTaskAttachments(id: string) {
  return useQuery({
    queryKey: taskQueryKeys.attachments(id),
    queryFn: ({ signal }) => listAttachments(id, signal),
  });
}

export function useTaskHistory(id: string) {
  return useQuery({
    queryKey: taskQueryKeys.history(id),
    queryFn: ({ signal }) => getTaskHistory(id, signal),
  });
}

export function useAssignableUsers(q: string, enabled: boolean) {
  return useQuery({
    queryKey: taskQueryKeys.assignable(q),
    queryFn: ({ signal }) => searchAssignable(q, signal),
    enabled,
    staleTime: 30_000,
  });
}

function useInvalidateTasks() {
  const client = useQueryClient();
  return () =>
    Promise.all([
      client.invalidateQueries({ queryKey: taskQueryKeys.all }),
      client.invalidateQueries({ queryKey: dashboardQueryKeys.summary }),
      client.invalidateQueries({ queryKey: notificationQueryKeys.all }),
    ]);
}

export function useCreateTask() {
  const invalidate = useInvalidateTasks();
  return useMutation({
    mutationFn: (input: TaskInput) => createTask(input),
    onSuccess: () => invalidate(),
  });
}

export function useUpdateTask(id: string) {
  const invalidate = useInvalidateTasks();
  return useMutation({
    mutationFn: (input: Partial<Omit<TaskInput, "assignee_ids">>) => updateTask(id, input),
    onSuccess: () => invalidate(),
  });
}

export function useChangeStatus(id: string) {
  const invalidate = useInvalidateTasks();
  return useMutation({
    mutationFn: (status: TaskStatus) => changeTaskStatus(id, status),
    onSuccess: () => invalidate(),
  });
}

export function useReplaceAssignees(id: string) {
  const invalidate = useInvalidateTasks();
  return useMutation({
    mutationFn: (userIds: string[]) => replaceAssignees(id, userIds),
    onSuccess: () => invalidate(),
  });
}

export function useDeleteTask(id: string) {
  const client = useQueryClient();
  const invalidate = useInvalidateTasks();
  return useMutation({
    mutationFn: () => deleteTask(id),
    onSuccess: async () => {
      client.removeQueries({ queryKey: taskQueryKeys.detail(id) });
      await invalidate();
    },
  });
}

export function useAddComment(id: string) {
  const invalidate = useInvalidateTasks();
  return useMutation({
    mutationFn: (body: string) => addComment(id, body),
    onSuccess: () => invalidate(),
  });
}

export function useEditComment(id: string) {
  const invalidate = useInvalidateTasks();
  return useMutation({
    mutationFn: ({ commentId, body }: { commentId: string; body: string }) =>
      editComment(id, commentId, body),
    onSuccess: () => invalidate(),
  });
}

export function useDeleteComment(id: string) {
  const invalidate = useInvalidateTasks();
  return useMutation({
    mutationFn: (commentId: string) => deleteComment(id, commentId),
    onSuccess: () => invalidate(),
  });
}

export function useUploadAttachment(id: string) {
  const invalidate = useInvalidateTasks();
  return useMutation({
    mutationFn: (file: File) => uploadAttachment(id, file),
    onSuccess: () => invalidate(),
  });
}

export function useDeleteAttachment(id: string) {
  const invalidate = useInvalidateTasks();
  return useMutation({
    mutationFn: (attachmentId: string) => deleteAttachment(id, attachmentId),
    onSuccess: () => invalidate(),
  });
}
