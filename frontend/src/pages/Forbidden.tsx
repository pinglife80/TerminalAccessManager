import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { ShieldOff, ArrowLeft } from 'lucide-react';
import branding from '@/config/branding';

const Forbidden: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: { pathname?: string } })?.from?.pathname;

  return (
    <div className="h-screen w-screen flex items-center justify-center bg-background">
      <div className="flex flex-col items-center space-y-6 max-w-md px-6 text-center">
        <div className="flex items-center justify-center w-20 h-20 rounded-full bg-red-100">
          <ShieldOff className="w-10 h-10 text-red-600" />
        </div>
        <div className="space-y-2">
          <h1 className="text-2xl font-semibold text-foreground">403 - Access Denied</h1>
          <p className="text-muted-foreground">
            You do not have permission to access this page.
            {from && (
              <span className="block mt-1 text-sm font-mono text-muted-foreground/70">{from}</span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate(-1)}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-md border border-input bg-background hover:bg-accent hover:text-accent-foreground transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Go Back
          </button>
          <button
            onClick={() => navigate('/dashboard', { replace: true })}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            Back to {branding.title}
          </button>
        </div>
      </div>
    </div>
  );
};

export default Forbidden;
