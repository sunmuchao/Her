"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

interface FeedbackOptionsPanelProps {
  sessionId: string;
  options: string[];
  promptMessage: string;
  onOptionSelect: (option: string) => void;
  onSkip: () => void;
}

export function FeedbackOptionsPanel({
  sessionId,
  options,
  promptMessage,
  onOptionSelect,
  onSkip,
}: FeedbackOptionsPanelProps) {
  const [selectedOption, setSelectedOption] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleOptionClick = async (option: string) => {
    setSelectedOption(option);
    setIsLoading(true);
    try {
      await onOptionSelect(option);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSkipClick = async () => {
    setIsLoading(true);
    try {
      await onSkip();
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Card className="feedback-options-panel p-4 mb-4">
      <div className="feedback-prompt mb-4 text-sm text-gray-700">
        {promptMessage}
      </div>

      <div className="options-grid grid gap-2">
        {options.map((option, index) => (
          <Button
            key={index}
            variant={selectedOption === option ? "default" : "outline"}
            className="feedback-option-button justify-start text-left h-auto py-2 px-3"
            onClick={() => handleOptionClick(option)}
            disabled={isLoading}
          >
            <span className="option-text">{option}</span>
          </Button>
        ))}
      </div>

      <div className="skip-section mt-3 pt-3 border-t border-gray-200">
        <Button
          variant="ghost"
          className="skip-button text-sm text-gray-500"
          onClick={handleSkipClick}
          disabled={isLoading}
        >
          跳过，直接换
        </Button>
      </div>

      {isLoading && (
        <div className="loading-indicator mt-3 text-center text-sm text-gray-500">
          正在调整搜索条件...
        </div>
      )}
    </Card>
  );
}

// 二级追问组件
interface SecondaryFeedbackPanelProps {
  sessionId: string;
  primaryFeedback: string;
  secondaryOptions: string[];
  secondaryPrompt: string;
  onSecondarySelect: (option: string) => void;
  onSkipSecondary: () => void;
}

export function SecondaryFeedbackPanel({
  sessionId,
  primaryFeedback,
  secondaryOptions,
  secondaryPrompt,
  onSecondarySelect,
  onSkipSecondary,
}: SecondaryFeedbackPanelProps) {
  const [selectedOption, setSelectedOption] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleSecondaryClick = async (option: string) => {
    setSelectedOption(option);
    setIsLoading(true);
    try {
      await onSecondarySelect(option);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSkipSecondaryClick = async () => {
    setIsLoading(true);
    try {
      await onSkipSecondary();
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Card className="secondary-feedback-panel p-4 mb-4 bg-blue-50">
      <div className="secondary-prompt mb-3 text-sm text-gray-700">
        {secondaryPrompt}
      </div>

      <div className="secondary-options-grid grid gap-2">
        {secondaryOptions.map((option, index) => (
          <Button
            key={index}
            variant={selectedOption === option ? "default" : "outline"}
            className="secondary-option-button justify-start text-left h-auto py-2 px-3"
            onClick={() => handleSecondaryClick(option)}
            disabled={isLoading}
          >
            <span className="option-text">{option}</span>
          </Button>
        ))}
      </div>

      {isLoading && (
        <div className="loading-indicator mt-3 text-center text-sm text-gray-500">
          正在调整搜索条件...
        </div>
      )}
    </Card>
  );
}