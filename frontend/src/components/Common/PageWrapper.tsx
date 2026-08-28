import { type ReactNode } from 'react';
import { Typography } from 'antd';

interface PageWrapperProps {
  children: ReactNode;
  title?: ReactNode;
  titleIcon?: ReactNode;
  extra?: ReactNode;
  className?: string;
}

/** Unified page container — provides consistent padding, header layout, and animation */
export function PageWrapper({ children, title, titleIcon, extra, className }: PageWrapperProps) {
  return (
    <div className={`gaf-page${className ? ` ${className}` : ''}`}>
      {(title || extra) && (
        <div className="gaf-page-header">
          <div className="gaf-page-title">
            {titleIcon && <span className="gaf-flex-center">{titleIcon}</span>}
            {title &&
              (typeof title === 'string' ? (
                <Typography.Title level={4} className="gaf-m-0 gaf-text-lg">
                  {title}
                </Typography.Title>
              ) : (
                title
              ))}
          </div>
          {extra && <div className="gaf-page-actions">{extra}</div>}
        </div>
      )}
      {children}
    </div>
  );
}

export default PageWrapper;
