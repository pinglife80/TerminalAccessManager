import React, { useState, useEffect } from 'react';
import { Calendar, X } from 'lucide-react';

interface DateRangeFilterProps {
  startDate: string;
  endDate: string;
  onChange: (dates: { startDate: string; endDate: string }) => void;
}

export const DateRangeFilter: React.FC<DateRangeFilterProps> = ({
  startDate,
  endDate,
  onChange,
}) => {
  const [error, setError] = useState<string>('');

  useEffect(() => {
    if (startDate && endDate && new Date(endDate) < new Date(startDate)) {
      setError('End date must be after start date');
    } else {
      setError('');
    }
  }, [startDate, endDate]);

  const handleStartDateChange = (value: string) => {
    // Always propagate the change, just show warning if invalid
    onChange({ startDate: value, endDate });
  };

  const handleEndDateChange = (value: string) => {
    // Always propagate the change, just show warning if invalid
    onChange({ startDate, endDate: value });
  };

  const handleClear = () => {
    setError('');
    onChange({ startDate: '', endDate: '' });
  };

  return (
    <div className="flex items-center gap-2">
      <div className="flex items-center gap-1.5 bg-gray-50 rounded-xl px-3 py-1.5">
        <Calendar className="h-4 w-4 text-gray-500 flex-shrink-0" />
        <input
          type="date"
          value={startDate}
          onChange={(e) => handleStartDateChange(e.target.value)}
          className="bg-transparent border-0 text-sm text-gray-700 focus:outline-none focus:ring-0 cursor-pointer font-medium w-[7.5rem]"
        />
        <span className="text-gray-400 text-xs font-medium">to</span>
        <input
          type="date"
          value={endDate}
          onChange={(e) => handleEndDateChange(e.target.value)}
          className={`bg-transparent border-0 text-sm focus:outline-none focus:ring-0 cursor-pointer font-medium w-[7.5rem] ${
            error ? 'text-red-500' : 'text-gray-700'
          }`}
        />
      </div>
      {(startDate || endDate) && (
        <button
          onClick={handleClear}
          className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
          title="Clear dates"
        >
          <X className="h-4 w-4" />
        </button>
      )}
      {error && (
        <span className="text-xs text-red-500 font-medium">{error}</span>
      )}
    </div>
  );
};
