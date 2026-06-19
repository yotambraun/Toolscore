// @ts-check
import { defineConfig } from 'astro/config';
import tailwind from '@astrojs/tailwind';

// Project page at https://yotambraun.github.io/Toolscore/
// `base` MUST be exactly '/Toolscore' (CamelCase, no trailing slash).
// All internal links/assets go through the url() helper in src/data/site.ts.
export default defineConfig({
  site: 'https://yotambraun.github.io',
  base: '/Toolscore',
  output: 'static',
  trailingSlash: 'ignore',
  integrations: [tailwind()],
});
