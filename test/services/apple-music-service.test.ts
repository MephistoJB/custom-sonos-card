import { afterEach, describe, expect, it, vi } from 'vitest';
import { AppleMusicService } from '../../src/services/apple-music-service';

describe('AppleMusicService', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('maps iTunes song results to Sonos Apple Music search items', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          resultCount: 2,
          results: [
            {
              wrapperType: 'track',
              kind: 'song',
              trackId: 636968288,
              trackName: 'Get Lucky',
              artistName: 'Daft Punk',
              collectionName: 'Random Access Memories',
              artworkUrl100: 'https://example.test/art/100x100bb.jpg',
            },
            {
              wrapperType: 'track',
              kind: 'music-video',
              trackId: 1,
              trackName: 'Filtered',
            },
          ],
        }),
        { status: 200 },
      ),
    );
    vi.stubGlobal('fetch', fetchMock);

    const results = await new AppleMusicService().search('Daft Punk', new Set(['track']), 5, {
      appleMusicAccountSn: '7',
      appleMusicCountry: 'DE',
    });

    expect(fetchMock).toHaveBeenCalledWith('https://itunes.apple.com/search?term=Daft+Punk&media=music&entity=song&limit=5&country=DE');
    expect(results).toEqual([
      {
        title: 'Get Lucky',
        subtitle: 'Daft Punk - Random Access Memories',
        uri: 'x-sonos-http:song%3a636968288.mp4?sid=204&flags=8224&sn=7',
        mediaType: 'track',
        imageUrl: 'https://example.test/art/600x600bb.jpg',
        artist: 'Daft Punk',
        album: 'Random Access Memories',
        itemId: '636968288',
        provider: 'apple_music',
      },
    ]);
  });

  it('returns no results when track search is disabled', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    const results = await new AppleMusicService().search('Daft Punk', new Set(['album']), 5, {});

    expect(results).toEqual([]);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
