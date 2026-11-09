import type { ReactElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { BackLink } from '../BackLink';
import { Card, CardContent, CardHeader } from '../Card';
import { ErrorState, NoDataEmpty, NoGamesEmpty } from '../EmptyState';
import { PagedList } from '../PagedList';
import { Pagination } from '../Pagination';
import { PlaylistSelect } from '../PlaylistSelect';
import { LoadingCards, SkeletonChart } from '../Skeleton';

const html = (element: ReactElement) => renderToStaticMarkup(<MemoryRouter>{element}</MemoryRouter>);
const noop = () => {};
const count = (text: string, part: string) => text.split(part).length - 1;

describe('Pagination', () => {
  it('shows nothing when the list fits on one page', () => {
    expect(html(<Pagination offset={0} total={20} onOffset={noop} />)).toBe('');
  });

  it('says which page you are on and stops Previous on the first', () => {
    const pager = html(<Pagination offset={0} total={45} onOffset={noop} />);
    expect(pager).toMatch(/Page (<!-- -->)?1(<!-- -->)? of (<!-- -->)?3/);
    expect(pager).toMatch(/disabled="">Previous/);
    expect(pager).not.toMatch(/disabled="">Next/);
  });

  it('stops Next on the last page', () => {
    const pager = html(<Pagination offset={40} total={45} onOffset={noop} />);
    expect(pager).toMatch(/disabled="">Next/);
    expect(pager).not.toMatch(/disabled="">Previous/);
  });
});

describe('PagedList', () => {
  const list = (items: string[], total = items.length) => ({ items, total, limit: 20, offset: 0 });
  const render = (props: Partial<Parameters<typeof PagedList<string>>[0]>) =>
    html(
      <PagedList<string>
        list={undefined}
        loading={false}
        failed={false}
        failure="The list didn't load."
        empty={<p>Nothing here</p>}
        offset={0}
        onOffset={noop}
        {...props}
      >
        {(items) => <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul>}
      </PagedList>,
    );

  it('says what failed before anything else', () => {
    const failed = render({ failed: true, loading: true, list: list(['a']) });
    expect(failed).toContain('The list didn&#x27;t load.');
    expect(failed).not.toContain('<li>');
  });

  it('shows ten rows of placeholders while it loads', () => {
    expect(count(render({ loading: true }), 'flex gap-4 p-3')).toBe(10);
  });

  it('shows what it was given for an empty list', () => {
    expect(render({ list: list([]) })).toContain('Nothing here');
  });

  it('shows the items, with the pager once there is more than a page', () => {
    expect(render({ list: list(['a', 'b']) })).toContain('<li>a</li><li>b</li>');
    expect(render({ list: list(['a', 'b']) })).not.toContain('Previous');
    expect(render({ list: list(['a', 'b'], 41) })).toContain('Previous');
  });
});

describe('empty states', () => {
  it('says what went wrong under a heading of its own', () => {
    const error = html(<ErrorState message="Trends didn't load." />);
    expect(error).toContain('Couldn&#x27;t load this');
    expect(error).toContain('Trends didn&#x27;t load.');
    expect(error).toContain('var(--chart-bad)');
  });

  it('draws a flat line in muted ink when there is just nothing yet', () => {
    const empty = html(<NoDataEmpty message="No games in this period" description="Try a longer period." />);
    expect(empty).toContain('No games in this period');
    expect(empty).toContain('Try a longer period.');
    expect(empty).not.toContain('var(--chart-bad)');
  });

  it('points a new install at the watch folder', () => {
    expect(html(<NoGamesEmpty />)).toContain('watch_folder');
  });
});

describe('cards', () => {
  it('adds the classes it is given to its own', () => {
    expect(html(<Card className="p-5">x</Card>)).toContain('border-[var(--color-border)] p-5"');
    expect(html(<CardHeader className="border-b">x</CardHeader>)).toContain('pb-3 border-b"');
    expect(html(<CardContent>x</CardContent>)).toContain('class="p-4 sm:p-5"');
  });

  it('loads a page as two placeholder cards, and a chart as one block', () => {
    expect(count(html(<LoadingCards />), 'rounded-md p-5 space-y-3')).toBe(2);
    expect(html(<SkeletonChart />)).toContain('h-72 w-full');
  });
});

describe('BackLink', () => {
  it('links back to the list by name', () => {
    const link = html(<BackLink to="/games">Games</BackLink>);
    expect(link).toContain('href="/games"');
    expect(link).toContain('</svg>Games</a>');
  });
});

describe('PlaylistSelect', () => {
  it('selects the playlist it is given', () => {
    expect(html(<PlaylistSelect value="DOUBLES" onChange={noop} />)).toContain(
      '<option value="DOUBLES" selected="">Doubles</option>',
    );
  });

  it('selects nothing until the playlist is known', () => {
    expect(html(<PlaylistSelect value={undefined} onChange={noop} />)).not.toContain('selected');
  });
});
