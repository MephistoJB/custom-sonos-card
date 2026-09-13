import { SearchConfig, SearchMediaType, SearchResultItem } from '../sections/search/search.types';

const APPLE_MUSIC_SERVICE_ID = '204';
const APPLE_MUSIC_FLAGS = '8224';
const DEFAULT_COUNTRY = 'DE';
const DEFAULT_ACCOUNT_SN = '5';

type ItunesEntity = 'song';

interface ItunesSearchTrack {
  wrapperType?: string;
  kind?: string;
  trackId?: number;
  trackName?: string;
  artistName?: string;
  collectionName?: string;
  artworkUrl100?: string;
  trackViewUrl?: string;
}

interface ItunesSearchResponse {
  resultCount: number;
  results: ItunesSearchTrack[];
}

export class AppleMusicService {
  async search(searchText: string, mediaTypes: Set<SearchMediaType>, searchLimit: number, config: SearchConfig): Promise<SearchResultItem[]> {
    const typesToSearch = mediaTypes.size > 0 ? Array.from(mediaTypes) : ['track'];
    if (!typesToSearch.includes('track')) {
      return [];
    }

    const response = await fetch(this.buildSearchUrl(searchText, searchLimit, config, 'song'));
    if (!response.ok) {
      throw new Error(`Apple Music search returned ${response.status}`);
    }

    const data = (await response.json()) as ItunesSearchResponse;
    const accountSn = `${config.appleMusicAccountSn ?? DEFAULT_ACCOUNT_SN}`;

    return data.results
      .filter((item) => item.wrapperType === 'track' && item.kind === 'song' && item.trackId && item.trackName)
      .map((item) => ({
        title: item.trackName!,
        subtitle: [item.artistName, item.collectionName].filter(Boolean).join(' - '),
        uri: this.buildSonosTrackUri(item.trackId!, accountSn),
        mediaType: 'track',
        imageUrl: this.upscaleArtwork(item.artworkUrl100),
        artist: item.artistName,
        album: item.collectionName,
        itemId: `${item.trackId}`,
        provider: 'apple_music',
      }));
  }

  private buildSearchUrl(searchText: string, searchLimit: number, config: SearchConfig, entity: ItunesEntity) {
    const params = new URLSearchParams({
      term: searchText.trim(),
      media: 'music',
      entity,
      limit: `${searchLimit}`,
      country: config.appleMusicCountry ?? DEFAULT_COUNTRY,
    });
    return `https://itunes.apple.com/search?${params.toString()}`;
  }

  private buildSonosTrackUri(trackId: number, accountSn: string) {
    return `x-sonos-http:song%3a${trackId}.mp4?sid=${APPLE_MUSIC_SERVICE_ID}&flags=${APPLE_MUSIC_FLAGS}&sn=${accountSn}`;
  }

  private upscaleArtwork(url?: string) {
    return url?.replace(/100x100bb\.(jpg|png|webp)$/, '600x600bb.$1');
  }
}
