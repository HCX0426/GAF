/**
 * Notification API
 * Covers notification list, unread count, mark read, batch operations,
 * and delete.
 */
import client from './client';

/** Notification item — matches backend NotificationSerializer */
export interface NotificationItem {
  id: number;
  title: string;
  content: string;
  category: string;
  is_read: boolean;
  related_url?: string | null;
  created_at: string;
}

/** Query params for the notification list endpoint */
export interface NotificationListParams {
  page: number;
  page_size: number;
  category?: string;
}

/**
 * Notification list response — backend may return either `{ items, total }`
 * (custom serializer) or `{ results, count }` (DRF paginated). Both shapes
 * are accepted so callers can fall back across fields.
 */
export interface NotificationListResponse {
  items?: NotificationItem[];
  results?: NotificationItem[];
  total?: number;
  count?: number;
}

/** Unread count response */
export interface UnreadCountResponse {
  unread_count: number;
}

/** Fetch a page of notifications, optionally filtered by category */
export async function fetchNotifications(params: NotificationListParams): Promise<NotificationListResponse> {
  const res = await client.get<NotificationListResponse>('/notifications/', { params });
  return res.data;
}

/** Fetch the current user's unread notification count */
export async function fetchUnreadCount(): Promise<UnreadCountResponse> {
  const res = await client.get<UnreadCountResponse>('/notifications/unread-count/');
  return res.data;
}

/** Mark a single notification as read */
export async function markNotificationRead(id: number): Promise<void> {
  await client.post(`/notifications/${id}/read/`);
}

/** Mark all notifications as read */
export async function markAllNotificationsRead(): Promise<void> {
  await client.post('/notifications/read-all/');
}

/** Delete a single notification by id */
export async function deleteNotification(id: number): Promise<void> {
  await client.delete(`/notifications/${id}/`);
}
