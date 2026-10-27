// Page guides shown by HelpButton.vue. Keep them short: what the page is for,
// the steps in order, and the mouse/keyboard controls.

export const HELP = {
  upload: {
    title: 'Getting started',
    intro: 'This tool turns a lidar tile (e.g. from USGS) into labelled training patches: every tree gets its own number.',
    sections: [
      {
        heading: 'The workflow',
        steps: [
          '<b>Load</b> a <code>.las</code> / <code>.laz</code> tile — drop it on this page.',
          '<b>2D view:</b> draw around an area to cut a <b>patch</b>, then click the patch in the list on the right.',
          '<b>3D view:</b> select each tree with the lasso and give it its own number. Mark ground.',
          '<b>Save</b> (Ctrl+S). The file goes to <code>data/labels</code>, named with the place, patch, your initials and the tree count.',
          'Check progress on <b>📊 Dataset</b>.',
        ],
      },
      {
        heading: 'Good to know',
        bullets: [
          'Every page has a <b>?</b> button in the top-right corner with its own short guide.',
          'Loaded files are kept on the server and removed after 24 h without use. Saved labels are never removed.',
          'Put your initials in <code>.env</code> (<code>LABELLER=…</code>) so your files are marked as yours.',
        ],
      },
    ],
  },

  view2d: {
    title: '2D view — cut patches',
    intro: 'The whole tile seen from above. Cut it into patches small enough to label comfortably (about 100 × 100 m works well).',
    sections: [
      {
        heading: 'Cut a patch',
        steps: [
          'Pick a tool in the toolbar:<br><b>Rectangle</b> — drag a box.<br><b>Freehand</b> — click the corners, <b>right-click</b> to close.<br><b>Fixed Rect</b> — draw once, then drag the same box to new places.',
          'The patch appears outlined and numbered, and in <b>Labeled Regions</b> on the right.',
          'Click it in that list to open it in 3D. A <b>C</b> means it has been saved.',
        ],
      },
      {
        heading: 'Move around',
        keys: [
          ['Mouse wheel', 'Zoom (detail sharpens after a moment)'],
          ['Right / middle drag', 'Pan'],
          ['Alt or Ctrl + drag', 'Pan (touchpads)'],
        ],
      },
      {
        heading: 'Also here',
        bullets: [
          '<b>Colour by</b>: elevation, classification, intensity or returns — classification shows buildings and ground nicely.',
          '<b>Whole Patch</b> opens the entire file in 3D (only for small files).',
          '<b>✂ Split</b> cuts a huge file into tiles and downloads them as a ZIP.',
          'The file list (▼) switches between loaded files and deletes them.',
          'A yellow units warning means the tool could only guess metres vs feet — check it, heights depend on it.',
        ],
      },
    ],
  },

  patch3d: {
    title: '3D view — label trees',
    intro: 'Give every tree its own number (101, 102, …). Points you leave alone keep their original class.',
    sections: [
      {
        heading: 'Label by hand',
        steps: [
          '<b>Look around</b> in rotate mode (↻): drag to rotate, right-drag to pan, wheel to zoom. <b>T</b> = top view, <b>S</b> = side view.',
          'Press <b>R</b> for the <b>lasso</b>: click around a tree, <b>right-click</b> to finish, Esc cancels.',
          'Press <b>Enter</b> or <b>Space</b>: the selection gets the current tree number, and the number moves on to the next one.',
          '<b>G</b> labels the selection as ground.',
          'Use the <b>elevation slider</b> (right edge) or <b>Clip Points</b> to hide points that are in the way.',
          '<b>Save</b> with Ctrl+S when done — saving again later replaces the file.',
        ],
      },
      {
        heading: 'Let the computer help',
        steps: [
          '<b>Run ▾</b> (or <b>I</b>): the neural network marks tree / non-tree points.',
          '<b>Segment Trees (CHM)</b> splits them into single trees. Hover a setting for what it does; <b>Min height</b> and <b>Min peak height</b> matter most.',
          'Looks right? <b>Apply to Labels</b>, then fix mistakes by hand with the lasso.',
        ],
      },
      {
        heading: 'Keys',
        keys: [
          ['R', 'Rotate ↔ lasso'],
          ['T / S', 'Top / side view'],
          ['V', 'Cycle colours (elevation, DTM, CHM)'],
          ['L', 'Show labels'],
          ['I', 'Run inference'],
          ['Enter / Space', 'Apply tree number'],
          ['G', 'Label as ground'],
          ['Ctrl+Z', 'Undo (200 steps)'],
          ['Ctrl+Y / Ctrl+Shift+Z', 'Redo'],
          ['Ctrl+S', 'Save'],
        ],
      },
    ],
  },

  dataset: {
    title: 'Dataset overview',
    intro: 'Everything that has been labelled, with tree counts per region. Changes here are saved straight away (in labelling_registry.json next to the labels).',
    sections: [
      {
        heading: 'Patches tab',
        bullets: [
          '<b>Double-click</b> a row to open the patch in 3D. Saving there updates the same file.',
          '<b>← Dataset</b> in the 3D view brings you back with your filters as they were.',
          '<b>✎</b> (hover a file name) renames the file in <code>data/labels</code>.',
          'Set a <b>status</b> (labelled, needs fix, reviewed, excluded) and notes to keep track. Excluded patches don\'t count in the totals.',
          '<b>By</b> shows who labelled it.',
        ],
      },
      {
        heading: 'Source tiles tab',
        bullets: [
          'One row per loaded tile. <b>City</b> and <b>state</b> go into the file names of its patches.',
          'Mark tiles <b>done</b> or <b>skipped</b> to see what is still missing.',
        ],
      },
      {
        heading: 'Buttons',
        bullets: [
          '<b>Rescan</b> after copying or editing files in <code>data/labels</code> outside the tool.',
          '<b>CSV</b> downloads the patch list for a spreadsheet.',
        ],
      },
    ],
  },
}
