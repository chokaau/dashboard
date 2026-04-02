/**
 * ConfigurationError — rendered when required env vars are missing (story-5-2).
 */

interface ConfigurationErrorProps {
  missing: string[];
}

export function ConfigurationError({ missing }: ConfigurationErrorProps) {
  return (
    <div
      role="alert"
      className="flex min-h-screen flex-col items-center justify-center gap-4 p-8 text-center"
    >
      <h1 className="text-2xl font-bold text-destructive">Configuration Error</h1>
      <p className="max-w-md text-muted-foreground">
        The following required environment variables are not set:
      </p>
      <ul className="rounded-md border border-destructive/40 bg-destructive/10 px-6 py-3 text-sm text-destructive">
        {missing.map((v) => (
          <li key={v} className="font-mono">
            {v}
          </li>
        ))}
      </ul>
      <p className="text-sm text-muted-foreground">
        Set these variables in your <code>.env</code> file and restart the dev
        server.
      </p>
    </div>
  );
}
