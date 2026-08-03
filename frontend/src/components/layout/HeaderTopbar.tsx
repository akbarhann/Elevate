import React from 'react';

interface HeaderTopbarProps {
  title: string;
  subtitle?: string;
}

export const HeaderTopbar: React.FC<HeaderTopbarProps> = ({ title }) => {
  return (
    <header className="h-16 bg-white border-b border-[#EBEBEF] px-8 flex items-center sticky top-0 z-10">
      <h1 className="text-sm font-semibold text-[#1A1A1F]">{title}</h1>
    </header>
  );
};
