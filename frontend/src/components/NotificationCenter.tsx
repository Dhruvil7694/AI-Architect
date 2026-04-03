"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { httpRequest } from "@/services/httpClient";
import FlowingMenu from './FlowingMenu';

interface NotificationItem {
  id: string;
  title: string;
  message: string;
  type: "success" | "info" | "warning" | "error" | "ai_render";
  is_read: boolean;
  created_at: string;
}

const demoItems = [
  { link: '#', text: 'Mojave', image: 'https://picsum.photos/600/400?random=1' },
  { link: '#', text: 'Sonoma', image: 'https://picsum.photos/600/400?random=2' },
  { link: '#', text: 'Monterey', image: 'https://picsum.photos/600/400?random=3' },
  { link: '#', text: 'Sequoia', image: 'https://picsum.photos/600/400?random=4' }
];

export default function NotificationCenter() {
  const [isOpen, setIsOpen] = useState(false);
  const queryClient = useQueryClient();

  // Fetch notifications from API
  const { data: notifications = [] } = useQuery<NotificationItem[]>({
    queryKey: ["notifications"],
    queryFn: () => httpRequest<NotificationItem[]>("/api/notifications/"),
    refetchInterval: 30000, // Refresh every 30s
  });

  const unreadCount = notifications.filter((n) => !n.is_read).length;

  // Mark all as read mutation
  const markAllRead = useMutation({
    mutationFn: () => httpRequest("/api/notifications/mark_all_read/", { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });

  return (
    <div className="notification-center-container">
      <button className="notification-bell" onClick={() => setIsOpen(!isOpen)}>
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        {unreadCount > 0 && <span className="notification-badge">{unreadCount}</span>}
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            key="notification-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="notification-backdrop"
            onClick={() => setIsOpen(false)}
          />
        )}
        {isOpen && (
          <motion.div
            key="notification-dropdown"
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 10 }}
            className="notification-dropdown"
          >
            <div className="notification-header">
              <h3>Notifications</h3>
              <button onClick={() => markAllRead.mutate()} disabled={unreadCount === 0}>
                Mark all as read
              </button>
            </div>

            <div className="notification-list">
              {notifications.length === 0 ? (
                <>
                  <div style={{ height: '300px', position: 'relative' }}>
                    <FlowingMenu 
                      // eslint-disable-next-line @typescript-eslint/no-explicit-any
                      items={demoItems as any}
                      speed={15}
                      textColor="#ffffff"
                      bgColor="#060010"
                      marqueeBgColor="#ffffff"
                      marqueeTextColor="#060010"
                      borderColor="#ffffff"
                    />
                  </div>
                  <div className="notification-empty">No notifications yet.</div>
                </>
              ) : (
                notifications.map((n) => (
                  <div key={n.id} className={`notification-item ${n.is_read ? "read" : "unread"}`}>
                    <div className="notification-item-content">
                      <div className="notification-item-title">{n.title}</div>
                      <div className="notification-item-message">{n.message}</div>
                      <div className="notification-item-time">{new Date(n.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</div>
                    </div>
                    {!n.is_read && <div className="unread-dot" />}
                  </div>
                ))
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <style jsx>{`
        .notification-center-container {
          position: relative;
        }
        .notification-bell {
          background: none;
          border: none;
          color: #000;
          cursor: pointer;
          padding: 8px;
          position: relative;
          border-radius: 50%;
          transition: background 0.2s;
        }
        .notification-bell:hover {
          background: #f5f5f5;
        }
        .notification-badge {
          position: absolute;
          top: 6px;
          right: 6px;
          background: #f97316;
          color: #fff;
          font-size: 10px;
          font-weight: 800;
          width: 16px;
          height: 16px;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          border: 2px solid #fff;
        }
        .notification-backdrop {
          position: fixed;
          top: 0;
          left: 0;
          width: 100vw;
          height: 100vh;
          z-index: 1000;
        }
        .notification-dropdown {
          position: absolute;
          top: 50px;
          right: -10px;
          width: 380px;
          background: #fff;
          border-radius: 20px;
          box-shadow: 0 20px 50px rgba(0, 0, 0, 0.15);
          z-index: 1001;
          overflow: hidden;
          border: 1px solid #f0f0f0;
        }
        .notification-header {
          padding: 20px 24px;
          border-bottom: 1px solid #f0f0f0;
          display: flex;
          justify-content: space-between;
          align-items: center;
        }
        .notification-header h3 {
          margin: 0;
          font-size: 16px;
          font-weight: 800;
          letter-spacing: -0.5px;
        }
        .notification-header button {
          background: none;
          border: none;
          color: #f97316;
          font-size: 12px;
          font-weight: 600;
          cursor: pointer;
        }
        .notification-list {
          max-height: 400px;
          overflow-y: auto;
        }
        .notification-item {
          padding: 16px 24px;
          border-bottom: 1px solid #fafafa;
          display: flex;
          align-items: center;
          gap: 12px;
          transition: background 0.2s;
        }
        .notification-item:hover {
          background: #fafafa;
        }
        .notification-item.unread {
          background: rgba(249, 115, 22, 0.02);
        }
        .notification-item-content {
          flex: 1;
        }
        .notification-item-title {
          font-size: 14px;
          font-weight: 700;
          color: #000;
          margin-bottom: 4px;
        }
        .notification-item-message {
          font-size: 13px;
          color: #666;
          line-height: 1.4;
        }
        .notification-item-time {
          font-size: 11px;
          color: #aaa;
          margin-top: 6px;
        }
        .unread-dot {
          width: 8px;
          height: 8px;
          background: #f97316;
          border-radius: 50%;
        }
        .notification-empty {
          padding: 40px;
          text-align: center;
          color: #aaa;
          font-size: 14px;
        }
      `}</style>
    </div>
  );
}
