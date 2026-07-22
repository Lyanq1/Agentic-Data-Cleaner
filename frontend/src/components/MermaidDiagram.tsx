import { useEffect, useId, useState } from 'react';

type MermaidApi = (typeof import('mermaid'))['default'];

interface MermaidDiagramProps {
  definition: string;
  className?: string;
}

let mermaidPromise: Promise<MermaidApi> | null = null;
let diagramSequence = 0;

function loadMermaid(): Promise<MermaidApi> {
  if (!mermaidPromise) {
    mermaidPromise = import('mermaid').then(({ default: mermaid }) => {
      mermaid.initialize({
        startOnLoad: false,
        securityLevel: 'strict',
        theme: 'base',
        themeVariables: {
          background: '#ffffff',
          fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif',
          lineColor: '#64748b',
          primaryColor: '#e0e7ff',
          primaryBorderColor: '#4f46e5',
          primaryTextColor: '#312e81',
          secondaryColor: '#cffafe',
          tertiaryColor: '#dcfce7',
        },
        flowchart: {
          curve: 'basis',
          nodeSpacing: 48,
          rankSpacing: 64,
          padding: 18,
        },
      });
      return mermaid;
    });
  }

  return mermaidPromise;
}

export function MermaidDiagram({ definition, className = '' }: MermaidDiagramProps) {
  const reactId = useId();
  const [rendered, setRendered] = useState({
    source: '',
    svg: '',
    error: null as string | null,
  });
  const source = definition.trim();
  const currentRender = rendered.source === source ? rendered : null;

  useEffect(() => {
    let cancelled = false;

    if (!source) {
      return () => {
        cancelled = true;
      };
    }

    diagramSequence += 1;
    const diagramId = `mermaid-${reactId.replace(/[^a-zA-Z0-9_-]/g, '')}-${diagramSequence}`;

    void loadMermaid()
      .then((mermaid) => mermaid.render(diagramId, source))
      .then((result) => {
        if (!cancelled) {
          setRendered({ source, svg: result.svg, error: null });
        }
      })
      .catch((renderError: unknown) => {
        if (cancelled) return;
        console.error('Failed to render Mermaid diagram:', renderError);
        setRendered({ source, svg: '', error: 'Unable to render this diagram.' });
      });

    return () => {
      cancelled = true;
    };
  }, [reactId, source]);

  if (!source) {
    return (
      <div className={`rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive ${className}`}>
        Diagram is not available yet.
      </div>
    );
  }

  if (currentRender?.error) {
    return (
      <div className={`rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive ${className}`}>
        {currentRender.error}
      </div>
    );
  }

  if (!currentRender?.svg) {
    return (
      <div className={`flex min-h-40 items-center justify-center rounded-lg border bg-muted/10 p-4 text-sm text-muted-foreground ${className}`}>
        Rendering diagram...
      </div>
    );
  }

  return (
    <div
      className={`overflow-auto rounded-lg border border-slate-200 bg-gradient-to-br from-slate-50 via-white to-blue-50/70 p-5 shadow-inner [&_svg]:mx-auto [&_svg]:h-auto [&_svg]:max-w-full ${className}`}
      role="img"
      aria-label="Data lineage diagram"
      dangerouslySetInnerHTML={{ __html: currentRender.svg }}
    />
  );
}
