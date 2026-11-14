import { sveltekit } from '@sveltejs/kit/vite';
import adapter from '@sveltejs/adapter-static';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [
		sveltekit({
			// Single-page app: the Rust API serves build/ and falls back to index.html.
			adapter: adapter({ pages: 'build', assets: 'build', fallback: 'index.html' })
		})
	],
	server: {
		proxy: {
			'/api': 'http://127.0.0.1:8080'
		}
	}
});
