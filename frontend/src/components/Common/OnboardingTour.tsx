/**
 * OnboardingTour — onboarding Tour
 *
 * Auto-pops up a 5-step guide on first visit, helps users quickly understand GAF core features.
 * Uses the useOnboardingTour hook for state management and the Antd Tour component for rendering.
 */

import { useEffect } from 'react';
import { Tour } from 'antd';
import type { TourProps } from 'antd';
import { useOnboardingTour, type TourStep } from '@/hooks/useOnboardingTour';

interface OnboardingTourProps {
  /** whether to force show (ignores localStorage state) */
  forceShow?: boolean;
  /** whether the user just logged in for the first time */
  isFirstLogin?: boolean;
  /** callback when onboarding completes */
  onComplete?: () => void;
  /** callback when user skips onboarding */
  onSkip?: () => void;
}

export function OnboardingTour({ forceShow, isFirstLogin, onComplete, onSkip }: OnboardingTourProps) {
  const { steps, currentStep, isActive, isCompleted, start, next, prev, skip, complete } = useOnboardingTour();

  /** Trigger tour automatically on first login or when forceShow is set */
  useEffect(() => {
    if (forceShow) {
      start();
      return;
    }
    if (isFirstLogin && !isCompleted) {
      const timer = setTimeout(start, 800);
      return () => clearTimeout(timer);
    }
  }, [forceShow, isFirstLogin, isCompleted, start]);

  const handleClose = () => {
    skip();
    onSkip?.();
  };

  const handleFinish = () => {
    complete();
    onComplete?.();
  };

  const tourSteps: TourProps['steps'] = steps.map((step: TourStep) => ({
    target: (() => document.querySelector(step.target) as HTMLElement | null) as () => HTMLElement,
    title: step.title,
    description: step.content,
    placement: step.placement,
  }));

  return (
    <Tour
      open={isActive}
      onClose={handleClose}
      steps={tourSteps}
      current={currentStep}
      onChange={(value: number) => {
        if (value > currentStep) {
          next();
        } else if (value < currentStep) {
          prev();
        }
      }}
      onFinish={handleFinish}
      indicatorsRender={(_currentDot: number, totalSteps: number) => (
        <div className="gaf-flex" style={{ gap: 6, justifyContent: 'center' }}>
          {Array.from({ length: totalSteps }).map((_, idx) => (
            <div
              key={`dot-${idx}`}
              style={{
                width: idx === currentStep ? 24 : 8,
                height: 8,
                borderRadius: 4,
                backgroundColor: idx <= currentStep ? '#1890ff' : '#d9d9d9',
                transition: 'width 0.3s ease, background-color 0.3s ease',
              }}
            />
          ))}
        </div>
      )}
    />
  );
}

export default OnboardingTour;
