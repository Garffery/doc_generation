import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { fetchTicketDetail } from '../api';
import ReportView from '../components/ReportView';

interface TicketDetail {
  id: string;
  message: string;
  status: string;
  created_at: string;
  report: {
    research_brief?: string;
    draft_report?: string;
    final_report?: string;
  };
}

const TABS = [
  { key: 'research_brief', label: '需求拆解' },
  { key: 'draft_report', label: '文档草稿' },
  { key: 'final_report', label: '最终报告' },
] as const;

type TabKey = (typeof TABS)[number]['key'];

export default function TicketDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [ticket, setTicket] = useState<TicketDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<TabKey>('final_report');

  useEffect(() => {
    if (!id) return;
    fetchTicketDetail(id)
      .then(setTicket)
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center text-gray-400 text-sm">加载中...</div>
    );
  }

  if (!ticket) {
    return (
      <div className="h-full flex items-center justify-center text-gray-400 text-sm">工单不存在</div>
    );
  }

  const tabContent = ticket.report[activeTab] || '';

  return (
    <div className="h-full flex flex-col">
      <header className="shrink-0 border-b border-orange-300 dark:border-orange-700 bg-orange-50 dark:bg-orange-950 px-6 py-4">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/tickets')}
            className="text-orange-600 hover:text-orange-700 dark:text-orange-400"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
              <polyline points="15 18 9 12 15 6" />
            </svg>
          </button>
          <div>
            <h1 className="text-xl font-bold text-orange-700 dark:text-orange-300">工单详情</h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5 truncate max-w-lg">
              {ticket.message}
            </p>
          </div>
        </div>
      </header>

      <nav className="shrink-0 flex border-b border-orange-300 dark:border-orange-700 px-4 bg-orange-50 dark:bg-orange-950">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab.key
                ? 'border-orange-500 text-orange-600 dark:border-orange-400 dark:text-orange-400'
                : 'border-transparent text-gray-500 hover:text-orange-500 dark:text-gray-400 dark:hover:text-orange-300'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      <div className="flex-1 overflow-y-auto p-6 bg-orange-50 dark:bg-orange-950">
        {tabContent ? (
          <ReportView content={tabContent} />
        ) : (
          <div className="flex items-center justify-center h-full text-gray-400 dark:text-gray-600 text-sm">
            暂无内容
          </div>
        )}
      </div>
    </div>
  );
}
