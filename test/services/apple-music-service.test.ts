import { afterEach, describe, expect, it, vi } from 'vitest';
import { AppleMusicService } from '../../src/services/apple-music-service';

describe('AppleMusicService', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('searches the Home Assistant Sonos backend for catalog results', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    const fetchWithAuth = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          items: [
            {
              title: 'Get Lucky',
              artist: 'Daft Punk',
              album: 'Random Access Memories',
              track_id: 'song:636968288',
              media_content_id: 'soco://0fffffffsong%253A636968288?sid=204&sn=0',
              media_content_type: 'track',
              thumbnail: 'https://example.test/art/600x600bb.jpg',
              provider: 'apple_music',
              source: 'catalog',
              didl: '<DIDL-Lite></DIDL-Lite>',
            },
          ],
        }),
        { status: 200 },
      ),
    );

    const results = await new AppleMusicService({ fetchWithAuth } as never).search('Daft Punk', new Set(['track']), 5, {
      appleMusicCountry: 'DE',
    });

    expect(fetchWithAuth).toHaveBeenCalledWith('/api/sonos_apple_music/search?query=Daft+Punk&limit=5&country=DE&account_sn=5&source=catalog');
    expect(fetchMock).not.toHaveBeenCalled();
    expect(results).toEqual([
      {
        title: 'Get Lucky',
        subtitle: 'Daft Punk - Random Access Memories',
        uri: 'soco://0fffffffsong%253A636968288?sid=204&sn=0',
        mediaType: 'track',
        imageUrl: 'https://example.test/art/600x600bb.jpg',
        artist: 'Daft Punk',
        album: 'Random Access Memories',
        itemId: 'song:636968288',
        provider: 'apple_music',
        inLibrary: false,
        didl: '<DIDL-Lite></DIDL-Lite>',
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

  it('searches the Home Assistant backend when library filter is active', async () => {
    const fetchWithAuth = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          items: [
            {
              title: 'Die Eine',
              artist: 'Die Firma',
              album: 'Das zweite Kapitel',
              track_id: 'i.ZzRKaFK94WVE',
              media_content_id: 'x-sonos-http:librarytrack%3ai.ZzRKaFK94WVE.mp4?sid=204&flags=8232&sn=5',
              media_content_type: 'track',
              thumbnail: 'https://example.test/art/600x600bb.jpg',
              provider: 'apple_music',
              source: 'library',
            },
          ],
        }),
        { status: 200 },
      ),
    );

    const service = new AppleMusicService({ fetchWithAuth } as never);
    const results = await service.search('Die Eine', new Set(['track']), 10, { appleMusicCountry: 'DE' }, 'library');

    expect(fetchWithAuth).toHaveBeenCalledWith('/api/sonos_apple_music/search?query=Die+Eine&limit=10&country=DE&account_sn=5&source=library');
    expect(results).toEqual([
      {
        title: 'Die Eine',
        subtitle: 'Die Firma - Das zweite Kapitel',
        uri: 'x-sonos-http:librarytrack%3ai.ZzRKaFK94WVE.mp4?sid=204&flags=8232&sn=5',
        mediaType: 'track',
        imageUrl: 'https://example.test/art/600x600bb.jpg',
        artist: 'Die Firma',
        album: 'Das zweite Kapitel',
        itemId: 'i.ZzRKaFK94WVE',
        provider: 'apple_music',
        inLibrary: true,
      },
    ]);
  });

  it('starts Sonos Apple Music authentication through Home Assistant', async () => {
    const callWS = vi.fn().mockResolvedValue({
      response: {
        app_url: 'sonos-2://x-callback-url/addAccount?callbackUrl=http%3A%2F%2Fhomeassistant.local%3A8123%2Fcallback',
        service_id: '204',
      },
    });

    const response = await new AppleMusicService({ callWS } as never).beginAuthentication('media_player.eg_gb_sonos', 'http://homeassistant.local:8123');

    expect(callWS).toHaveBeenCalledWith({
      type: 'call_service',
      domain: 'sonos_apple_music',
      service: 'auth_begin',
      target: { entity_id: 'media_player.eg_gb_sonos' },
      service_data: { base_url: 'http://homeassistant.local:8123' },
      return_response: true,
    });
    expect(response.app_url).toContain('sonos-2://x-callback-url/addAccount');
  });

  it('reads nested auth responses returned by targeted service calls', async () => {
    const callWS = vi.fn().mockResolvedValue({
      response: {
        'media_player.eg_gb_sonos': {
          app_url: 'sonos-2://x-callback-url/addAccount',
        },
      },
    });

    const response = await new AppleMusicService({ callWS } as never).beginAuthentication('media_player.eg_gb_sonos');

    expect(response.app_url).toBe('sonos-2://x-callback-url/addAccount');
  });
});
