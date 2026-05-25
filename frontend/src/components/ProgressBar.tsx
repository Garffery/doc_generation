interface ProgressBarProps {
  stage: string;
  message: string;
}

const STAGES = [
  'write_research_brief',
  'question_to_user',
  'write_draft_report',
  'supervisor_subgraph',
  'final_report_generation',
];

const STAGE_LABELS: Record<string, string> = {
  write_research_brief: '需求拆解',
  question_to_user: '需求澄清',
  write_draft_report: '文档草稿',
  supervisor_subgraph: '深度研究',
  final_report_generation: '最终报告',
};

export default function ProgressBar({ stage, message }: ProgressBarProps) {
  const currentIndex = STAGES.indexOf(stage);
  const progress = currentIndex >= 0 ? ((currentIndex + 1) / STAGES.length) * 100 : 0;

  return (
    <div className="w-full space-y-3">
      <div className="flex justify-between text-sm text-gray-600 dark:text-gray-400">
        <span>{message}</span>
        <span>{Math.round(progress)}%</span>
      </div>

      <div className="w-full h-2 bg-gray-200 rounded-full dark:bg-gray-700">
        <div
          className="h-full bg-blue-600 rounded-full transition-all duration-500 dark:bg-blue-500"
          style={{ width: `${progress}%` }}
        />
      </div>

      <div className="flex justify-between">
        {STAGES.map((s, i) => (
          <div
            key={s}
            className={`text-xs px-2 py-1 rounded ${
              i <= currentIndex
                ? 'text-blue-700 bg-blue-100 dark:text-blue-300 dark:bg-blue-900'
                : 'text-gray-400 dark:text-gray-600'
            }`}
          >
            {STAGE_LABELS[s]}
          </div>
        ))}
      </div>
    </div>
  );
}
