/**
 * Route table.
 *
 * Only the arena exists today. The main menu, room browser and invite links
 * (`/r/:code`) slot in here as siblings — `ArenaScreen` already tears its game
 * down on unmount, so navigating away is safe.
 */

import { createBrowserRouter } from 'react-router';
import { ArenaScreen } from '../screens/ArenaScreen';

export const router = createBrowserRouter([
  {
    path: '/',
    Component: ArenaScreen,
  },
]);
