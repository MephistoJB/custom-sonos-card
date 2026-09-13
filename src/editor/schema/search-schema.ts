const mediaTypeOptions = {
  none: 'None',
  track: 'Track',
  artist: 'Artist',
  album: 'Album',
  playlist: 'Playlist',
  radio: 'Radio',
};

const viewModeOptions = {
  list: 'List',
  grid: 'Grid',
};

const appleMusicSourceOptions = {
  catalog: 'Catalog',
  library: 'Library',
  all: 'Catalog and library',
};

export const SEARCH_SCHEMA = [
  {
    name: 'title',
    type: 'string',
    help: 'Custom title for the search section',
  },
  {
    name: 'hideActivePlayerName',
    selector: { boolean: {} },
    help: 'Hide active player/group name in the search header',
  },
  {
    name: 'massConfigEntryId',
    type: 'string',
    help: 'Leave empty to auto-discover',
  },
  {
    name: 'appleMusicAccountSn',
    type: 'string',
    help: 'Sonos Apple Music account number, e.g. 5',
  },
  {
    name: 'appleMusicCountry',
    type: 'string',
    help: 'Reserved for Sonos Apple Music regional behavior',
  },
  {
    type: 'select',
    options: Object.entries(appleMusicSourceOptions).map((entry) => entry),
    name: 'appleMusicSource',
    help: 'Apple Music search source for Sonos Apple Music mode',
  },
  {
    name: 'appleMusicAuthBaseUrl',
    type: 'string',
    help: 'Optional Home Assistant base URL for Apple Music Sonos auth callback',
  },
  {
    type: 'select',
    options: Object.entries(mediaTypeOptions).map((entry) => entry),
    name: 'defaultMediaType',
  },
  {
    type: 'select',
    options: Object.entries(viewModeOptions).map((entry) => entry),
    name: 'defaultViewMode',
    help: 'Default view mode (default: list)',
  },
  {
    name: 'gridColumns',
    type: 'integer',
    help: 'Number of columns in grid view (default: 4)',
  },
  {
    name: 'searchLimit',
    type: 'integer',
    help: 'Max results per search (default: 50)',
  },
  {
    name: 'autoSearchMinChars',
    type: 'integer',
    help: 'Min characters to trigger auto-search (default: 2)',
  },
  {
    name: 'autoSearchDebounceMs',
    type: 'integer',
    help: 'Debounce delay in ms (default: 1000)',
  },
];
