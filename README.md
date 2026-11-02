# linsolarsystem

An interactive 3D model of the solar system that runs in the browser. Visitors can watch the Sun and eight planets orbit in real time, change the speed of time, pause the simulation, and click any planet to fly the camera to it and read NASA-sourced facts about it.

It is built with Three.js, TypeScript, Vite and Bootstrap 5.

## What it demonstrates

- **Semantic HTML and structure.** A single entry page with a canvas for the 3D scene, a root element for the interface, and a loading overlay, using landmark elements and ARIA labels on the progress bar, buttons and sidebar.
- **CSS and responsive design.** Global styles with CSS variables, a translucent "glass" top bar and sidebar using `backdrop-filter`, and a layout that collapses into a menu on small screens.
- **Typography.** Web fonts loaded from Google Fonts, with a clear hierarchy: Afacad Flux for headings and DM Serif Text for body text.
- **A component framework.** Bootstrap 5 for the navbar, dropdown, form controls, progress bar and offcanvas sidebar, including its JavaScript API.
- **TypeScript.** Strict typing across the app, typed data models for planets and facts, and no unchecked DOM lookups.
- **Real-time 3D graphics.** A Three.js scene with a perspective camera, orbit controls, lighting, a star field, texture-mapped spheres, axial tilt, rotation, and orbital motion driven by a render loop.
- **Asset loading and performance.** Draco-compressed GLB models made in Blender, a shared loading manager that drives a real progress bar, placeholders that show before models arrive, and capped pixel ratio.
- **User interaction.** Raycasting to pick planets under the cursor, tell clicks apart from drags, smooth camera following, and a sidebar that shifts the view so the selected planet stays visible.
- **Data-driven UI.** Planet details live in a single typed data file and are rendered into the interface, so content is separate from code.
- **Tooling and build.** A Vite build pipeline with TypeScript checking and linting.

## Assets and credits

- Mars texture: [NASA 3D Resources](https://science.nasa.gov/3d-resources/mars/).
- Mercury texture: NASA/JHU APL/Carnegie Institution MESSENGER MDIS global mosaic ([PIA15063](https://photojournal.jpl.nasa.gov/catalog/PIA15063)).
- Planet facts: NASA planetary fact sheets.
- Sizes and distances in the scene are compressed for visibility and are not to scale.
