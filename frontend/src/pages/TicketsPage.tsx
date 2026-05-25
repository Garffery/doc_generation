import { useEffect, useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchTickets, fetchTicketDetail } from '../api';

interface Ticket {
  id: string;
  message: string;
  status: string;
  created_at: string;
}

const STATUS_LABELS: Record<string, { text: string; className: string }> = {
  pending: { text: '等待中', className: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400' },
  running: { text: '生成中', className: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300' },
  done: { text: '已完成', className: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300' },
  error: { text: '失败', className: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300' },
};

function downloadMarkdown(content: string, filename: string) {
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function TicketsPage() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(true);
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    fetchTickets()
      .then(setTickets)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpenId(null);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleDownload = async (ticketId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setMenuOpenId(null);
    const detail = await fetchTicketDetail(ticketId);
    const content = detail.report?.final_report;
    if (!content) {
      alert('该工单暂无最终报告');
      return;
    }
    downloadMarkdown(content, `report-${ticketId.slice(0, 8)}.md`);
  };

  return (
    <div className="h-full flex flex-col">
      <header className="shrink-0 border-b border-orange-300 dark:border-orange-700 bg-orange-50 dark:bg-orange-950 px-6 py-4 flex items-center justify-between">
        <h1 className="text-xl font-bold text-orange-700 dark:text-orange-300">
          工单列表
        </h1>
        <button
          onClick={() => { setLoading(true); fetchTickets().then(setTickets).finally(() => setLoading(false)); }}
          className="text-sm text-orange-600 hover:text-orange-700 dark:text-orange-400"
        >
          刷新
        </button>
      </header>

      <div className="flex-1 overflow-y-auto bg-orange-50 dark:bg-orange-950 p-6">
        {loading ? (
          <div className="flex items-center justify-center h-full text-gray-400 text-sm">加载中...</div>
        ) : tickets.length === 0 ? (
          <div className="flex items-center justify-center h-full text-gray-400 dark:text-gray-600 text-sm">暂无工单</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-xs uppercase text-gray-500 dark:text-gray-400 border-b border-orange-200 dark:border-orange-800">
                <tr>
                  <th className="px-4 py-3">工单ID</th>
                  <th className="px-4 py-3">需求描述</th>
                  <th className="px-4 py-3">状态</th>
                  <th className="px-4 py-3">创建时间</th>
                  <th className="px-4 py-3 w-12"></th>
                </tr>
              </thead>
              <tbody>
                {tickets.map((ticket) => {
                  const status = STATUS_LABELS[ticket.status] || STATUS_LABELS.pending;
                  return (
                    <tr
                      key={ticket.id}
                      onClick={() => navigate(`/tickets/${ticket.id}`)}
                      className="border-b border-orange-100 dark:border-orange-900 hover:bg-orange-100 dark:hover:bg-orange-900/30 cursor-pointer transition-colors"
                    >
                      <td className="px-4 py-3 font-mono text-xs text-gray-500 dark:text-gray-400">
                        {ticket.id.slice(0, 8)}...
                      </td>
                      <td className="px-4 py-3 text-gray-800 dark:text-gray-200 max-w-md truncate">
                        {ticket.message}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${status.className}`}>
                          {status.text}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-500 dark:text-gray-400 whitespace-nowrap">
                        {new Date(ticket.created_at).toLocaleString('zh-CN')}
                      </td>
                      <td className="px-4 py-3 relative">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setMenuOpenId(menuOpenId === ticket.id ? null : ticket.id);
                          }}
                          className="p-1 rounded hover:bg-orange-200 dark:hover:bg-orange-800 text-gray-500 dark:text-gray-400"
                        >
                          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4">
                            <circle cx="12" cy="5" r="1.5" />
                            <circle cx="12" cy="12" r="1.5" />
                            <circle cx="12" cy="19" r="1.5" />
                          </svg>
                        </button>
                        {menuOpenId === ticket.id && (
                          <div
                            ref={menuRef}
                            className="absolute right-4 top-10 z-10 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg py-1 min-w-[140px]"
                          >
                            <button
                              onClick={(e) => handleDownload(ticket.id, e)}
                              className="w-full text-left px-4 py-2 text-sm text-gray-700 dark:text-gray-200 hover:bg-orange-50 dark:hover:bg-gray-700 flex items-center gap-2"
                            >
                              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
                                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                                <polyline points="7 10 12 15 17 10" />
                                <line x1="12" y1="15" x2="12" y2="3" />
                              </svg>
                              下载最终报告
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
