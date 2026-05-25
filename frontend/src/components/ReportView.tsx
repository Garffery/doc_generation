import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface ReportViewProps {
  content: string;
  title?: string;
}

export default function ReportView({ content, title }: ReportViewProps) {
  if (!content) return null;

  return (
    <div className="w-full text-left">
      {title && (
        <h2 className="text-lg font-semibold mb-3 text-gray-800 dark:text-gray-200">
          {title}
        </h2>
      )}
      <div className="report-markdown prose prose-base max-w-none dark:prose-invert
                      prose-headings:text-gray-800 dark:prose-headings:text-gray-100">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            pre: ({ children }) => (
              <pre style={{ backgroundColor: 'inherit', color: '#374151' }}>
                {children}
              </pre>
            ),
            code: ({ children, className }) => (
              <code
                className={className}
                style={{ backgroundColor: 'inherit', color: '#374151' }}
              >
                {children}
              </code>
            ),
          }}
        >
          {content}
        </ReactMarkdown>
      </div>
    </div>
  );
}
