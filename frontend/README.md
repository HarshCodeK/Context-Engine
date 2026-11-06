# Context Studio frontend

The frontend is a React + TypeScript application built with Vite, Tailwind CSS v4, and generated shadcn/ui components backed by Base UI.

## Development

Start the FastAPI backend on `127.0.0.1:8001`, then run:

```powershell
npm run dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/api` to the local backend.

## Production build

```powershell
npm run build
```

Vite writes the built app to the project root `dist/` directory. The root FastAPI entry point serves that directory under `/studio-assets/` and serves its `index.html` at `/`.

## Components and conventions

- Shared controls come from `src/components/ui/` and are generated shadcn/ui components.
- `components.json` uses the `@/` source alias and Tabler icons.
- `src/lib/api.ts` contains the small typed HTTP client.
- `src/features/workspace/` owns the upload queue and output review.
- `src/features/rules/` owns saved context-rule management.
- Geist is used for interface text and Geist Mono for technical metadata.
- The interface uses a restrained dark/light palette and respects reduced-motion preferences.

No additional frontend package is required for the current workflow.
