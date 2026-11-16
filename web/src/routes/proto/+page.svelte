<script lang="ts">
	import '../../app.css';

	const PROTOS = [
		{
			href: '/proto/now',
			name: 'A · Now',
			who: 'Fire responders, firefighters and duty officers',
			job: 'Is burning unusual right now, and where?',
			how: 'The map is the search: pan or zoom and every hexagon is coloured by how this month compares with its usual month. One answer sentence, a strip of recent months, and a tap on any hexagon. Works on a phone.'
		},
		{
			href: '/',
			name: 'B · Explore',
			who: 'Scientists, remote-sensing analysts and data journalists',
			job: 'How did burning change over 25 years, and can I trust each satellite era?',
			how: 'Kepler-style: dark map, a layer panel (colour, 3D height, opacity), and a time bar along the bottom with the whole series as a histogram, a brush for the date range and a play button that animates month by month.'
		},
		{
			href: '/proto/seasons',
			name: 'C · Seasons',
			who: 'Land managers, park and forestry planners, policy and NGO staff',
			job: 'When does my area burn, and was this year worse than last?',
			how: 'The burning calendar is the time control, docked under the map. Click a month or a year to map it, or compare two years as a change map. A typical-season profile shows when the fire season starts and peaks.'
		}
	];
</script>

<svelte:head><title>firecal UI prototypes</title></svelte:head>

<main>
	<h1>firecal: three map-first prototypes</h1>
	<p class="lede">
		Each prototype answers every challenge objective (choose an area, choose dates, the burning calendar, this month against the
		usual, downloads), with the map as the centrepiece. They differ in who they are built for. All run on the same API and data.
	</p>
	<div class="grid">
		{#each PROTOS as p (p.href)}
			<a class="card proto-card" href={p.href}>
				<h2>{p.name}</h2>
				<p class="who">{p.who}</p>
				<p class="job">"{p.job}"</p>
				<p>{p.how}</p>
			</a>
		{/each}
	</div>
	<p class="small"><a href="/">Current app</a></p>
</main>

<style>
	main {
		max-width: 1100px;
		margin: 0 auto;
		padding: 32px 16px;
	}
	h1 {
		font-size: 1.6rem;
		margin: 0 0 8px;
	}
	.lede {
		color: var(--text-2);
		max-width: 70ch;
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
		gap: 16px;
		margin: 24px 0;
	}
	.proto-card {
		color: inherit;
		text-decoration: none;
		display: block;
	}
	.proto-card:hover {
		border-color: var(--accent);
	}
	h2 {
		font-size: 1.15rem;
		margin: 0 0 4px;
	}
	.who {
		color: var(--accent);
		font-weight: 600;
		margin: 0 0 8px;
		font-size: 0.9rem;
	}
	.job {
		font-style: italic;
		margin: 0 0 8px;
	}
	p {
		font-size: 0.92rem;
	}
	.small {
		font-size: 0.85rem;
	}
</style>
