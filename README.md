# linsolarsystem

A React + TypeScript app built with Vite. It is currently the unmodified Vite starter (a counter and links), ready to be built into a solar system project.

## Stack

- React 19, TypeScript 6
- Vite 8 with `@vitejs/plugin-react`
- Oxlint for linting

## Getting started

Requires Node.js (a version supported by Vite 8).

```bash
npm install
npm run dev      # start the dev server with HMR
```

## Scripts

| Command           | What it does                                  |
| ----------------- | --------------------------------------------- |
| `npm run dev`     | Start the Vite dev server                     |
| `npm run build`   | Type-check (`tsc -b`) and build to `dist/`    |
| `npm run preview` | Serve the production build locally            |
| `npm run lint`    | Run Oxlint (config in `.oxlintrc.json`)       |

## Project layout

```
index.html        # Vite entry HTML
public/           # Static assets served as-is (favicon, icons.svg)
src/main.tsx      # React entry point
src/App.tsx       # Root component (starter content)
src/App.css       # App styles
src/index.css     # Global styles
src/assets/       # Imported images
```

## Optional next steps

- Enable [type-aware Oxlint rules](https://oxc.rs/docs/guide/usage/linter/rules) by installing `oxlint-tsgolint` and setting `"options": { "typeAware": true }` in `.oxlintrc.json`.
- Add the [React Compiler](https://react.dev/learn/react-compiler/installation) (off by default because of its dev/build cost).
