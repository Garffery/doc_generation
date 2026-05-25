import { useState, useRef } from 'react';
import InputForm from '../components/InputForm';
import ProgressBar from '../components/ProgressBar';
import ReportView from '../components/ReportView';
import ClarificationPanel from '../components/ClarificationPanel';
import { streamGenerate, streamResume } from '../api';
import type { SSEEvent } from '../api';

type AppState = 'idle' | 'generating' | 'awaiting_answers' | 'done' | 'error';

const STAGE_TABS = [
  { key: 'research_brief', label: '需求拆解' },
  { key: 'clarification', label: '需求澄清' },
  { key: 'draft_report', label: '文档草稿' },
  { key: 'final_report', label: '最终报告' },
] as const;

type TabKey = (typeof STAGE_TABS)[number]['key'];

export default function GeneratePage() {
  const [state, setState] = useState<AppState>('idle');
  const [stage, setStage] = useState('');
  const [stageMessage, setStageMessage] = useState('');
  const [researchBrief, setResearchBrief] = useState('');
  const [draftReport, setDraftReport] = useState('');
  const [finalReport, setFinalReport] = useState('');
  const [error, setError] = useState('');
  const [threadId, setThreadId] = useState('');
  const [questions, setQuestions] = useState<{question: string, options: string[]}[]>([]);
  const [activeTab, setActiveTab] = useState<TabKey>('research_brief');
  const controllerRef = useRef<AbortController | null>(null);

  const handleSSEEvent = (event: SSEEvent) => {
    switch (event.type) {
      case 'session':
        setThreadId(event.data.thread_id);
        break;
      case 'status':
        setStage(event.data.stage);
        setStageMessage(event.data.message);
        if (event.data.stage === 'write_research_brief') setActiveTab('research_brief');
        else if (event.data.stage === 'question_to_user') setActiveTab('clarification');
        else if (event.data.stage === 'write_draft_report') setActiveTab('draft_report');
        else if (event.data.stage === 'final_report_generation') setActiveTab('final_report');
        break;
      case 'progress':
        if (event.data.stage === 'research_brief') {
          setResearchBrief(event.data.content);
        } else if (event.data.stage === 'draft_report') {
          setDraftReport(event.data.content);
        }
        break;
      case 'interrupt': {
        setThreadId(event.data.thread_id);
        try {
          const parsed = JSON.parse(event.data.questions);
          setQuestions(parsed);
        } catch {
          setQuestions([]);
        }
        setState('awaiting_answers');
        setActiveTab('clarification');
        break;
      }
      case 'result':
        setFinalReport(event.data.content);
        setActiveTab('final_report');
        break;
      case 'error':
        setError(event.data.message);
        setState('error');
        break;
    }
  };

  const handleSubmit = (message: string) => {
    setState('generating');
    setStage('');
    setStageMessage('准备中...');
    setResearchBrief('');
    setDraftReport('');
    setFinalReport('');
    setError('');
    setThreadId('');
    setQuestions([]);
    setActiveTab('research_brief');

    const controller = streamGenerate(
      message,
      handleSSEEvent,
      (err) => {
        setError(err.message);
        setState('error');
      },
      () => {
        if (state !== 'awaiting_answers') {
          setState((prev) => (prev === 'generating' ? 'done' : prev));
        }
      },
    );

    controllerRef.current = controller;
  };

  const handleAnswerSubmit = (answers: string) => {
    setState('generating');
    setStageMessage('正在处理您的回答...');

    const controller = streamResume(
      threadId,
      answers,
      handleSSEEvent,
      (err) => {
        setError(err.message);
        setState('error');
      },
      () => {
        setState('done');
      },
    );

    controllerRef.current = controller;
  };

  const handleStop = () => {
    controllerRef.current?.abort();
    setState('done');
  };

  const renderTabContent = () => {
    switch (activeTab) {
      case 'research_brief':
        return researchBrief
          ? <ReportView content={researchBrief} />
          : <EmptyHint text="需求拆解产物将在此显示" />;
      case 'clarification':
        if (state === 'awaiting_answers' && questions.length > 0) {
          return (
            <ClarificationPanel
              questions={questions}
              onSubmit={handleAnswerSubmit}
              disabled={false}
            />
          );
        }
        return <EmptyHint text="需求澄清内容将在此显示" />;
      case 'draft_report':
        return draftReport
          ? <ReportView content={draftReport} />
          : <EmptyHint text="文档草稿将在此显示" />;
      case 'final_report':
        return finalReport
          ? <ReportView content={finalReport} />
          : <EmptyHint text="最终报告将在此显示" />;
    }
  };

  return (
    <div className="h-full flex flex-col">
      <header className="shrink-0 border-b border-orange-300 dark:border-orange-700 bg-orange-50 dark:bg-orange-950 px-6 py-4">
        <h1 className="text-xl font-bold text-orange-700 dark:text-orange-300">
          文档生成
        </h1>
      </header>

      <div className="flex-1 flex overflow-hidden">
        {/* 左侧：输入区 */}
        <aside className="w-[380px] shrink-0 border-r border-orange-300 dark:border-orange-700 bg-orange-50 dark:bg-orange-950 p-5 flex flex-col overflow-y-auto">
          <div className="flex-1 flex flex-col">
            <InputForm onSubmit={handleSubmit} disabled={state === 'generating' || state === 'awaiting_answers'} />
          </div>

          {state === 'generating' && (
            <div className="shrink-0 space-y-3 mt-4">
              <ProgressBar stage={stage} message={stageMessage} />
              <button
                onClick={handleStop}
                className="text-sm text-red-600 hover:text-red-700 dark:text-red-400"
              >
                停止生成
              </button>
            </div>
          )}

          {error && (
            <div className="shrink-0 mt-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3 text-sm text-red-700 dark:text-red-300">
              {error}
            </div>
          )}
        </aside>

        {/* 右侧：阶段页签 + 产物展示 */}
        <main className="flex-1 flex flex-col overflow-hidden bg-orange-50 dark:bg-orange-950">
          <nav className="shrink-0 flex border-b border-orange-300 dark:border-orange-700 px-4">
            {STAGE_TABS.map((tab) => (
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

          <div className="flex-1 overflow-y-auto p-6">
            {renderTabContent()}
          </div>
        </main>
      </div>
    </div>
  );
}

function EmptyHint({ text }: { text: string }) {
  return (
    <div className="flex items-center justify-center h-full text-gray-400 dark:text-gray-600 text-sm">
      {text}
    </div>
  );
}
